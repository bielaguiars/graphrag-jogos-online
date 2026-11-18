"""Resolucao de entidades (Entity Resolution / canonicalizacao).

Tres passos:
1. chave lexical: minusculas, sem pontuacao, sem plural simples e sem sigla entre parenteses;
2. aliases: duas mencoes do mesmo tipo se fundem se o nome de uma bate com um alias da
   outra e os nomes sao compativeis (mesma grafia, sigla ou trigramas parecidos);
3. semantica: embeddings com cosseno >= limiar E trigramas parecidos (>= 0.85), so dentro do
   mesmo tipo e sem conflito de numeros (evita fundir GPT-3 com GPT-4 ou Llama 2 com Llama 3).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

_PAREN = re.compile(r"\s*\([^)]*\)")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def norm_key(name: str) -> str:
    s = _PAREN.sub("", name.lower()).strip() or name.lower()
    s = _NON_ALNUM.sub(" ", s).strip()
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
             for w in s.split()]
    return " ".join(words)


def slug(name: str) -> str:
    # mantem o conteudo dos parenteses: "Final Fantasy XIV (2010)" != "Final Fantasy XIV"
    return _NON_ALNUM.sub("-", name.lower()).strip("-") or "x"


def digits(name: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", name))


_GENERIC = {"method", "algorithm", "model", "approach", "framework", "technique", "the"}


def _trigrams(name: str) -> set[str]:
    core = "".join(w for w in norm_key(name).split() if w not in _GENERIC)
    return {core[i:i + 3] for i in range(max(1, len(core) - 2))}


def lexical_sim(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def is_acronym(short: str, long: str) -> bool:
    s = re.sub(r"[^a-z]", "", short.lower())
    words = norm_key(long).split()
    if len(s) < 2 or len(words) < 2:
        return False
    initials = "".join(w[0] for w in words)
    small = {"of", "the", "for", "and", "in", "on", "with"}
    return s in (initials, "".join(w[0] for w in words if w not in small))


_CORP = {"corporation", "corp", "inc", "ltd", "limited", "llc", "co", "company", "studio",
         "studios", "entertainment", "game", "games", "interactive", "holding", "holdings",
         "group", "the"}


def _corp_core(name: str) -> str:
    return " ".join(w for w in norm_key(name).split() if w not in _CORP)


def compatible(a: str, b: str) -> bool:
    """Dois nomes podem ser a mesma entidade? Barra aliases mal atribuidos pelo extrator."""
    if digits(a) != digits(b):
        return False
    return (norm_key(a) == norm_key(b) or is_acronym(a, b) or is_acronym(b, a)
            or lexical_sim(a, b) >= 0.5
            or bool(_corp_core(a)) and _corp_core(a) == _corp_core(b)  # Valve ~ Valve Corporation
            or norm_key(a.split(":")[0]) == norm_key(b.split(":")[0]))  # Warcraft III ~ Warcraft III: Reign of Chaos


@dataclass
class Mention:
    name: str
    type: str
    aliases: list[str]
    description: str
    doc_id: str


@dataclass
class Canonical:
    id: str
    name: str
    type: str
    aliases: list[str]
    description: str
    docs: list[str] = field(default_factory=list)
    surface_forms: list[str] = field(default_factory=list)


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


def resolve(mentions: list[Mention], embed=None, threshold: float = 0.93
            ) -> tuple[list[Canonical], dict[tuple[str, str], str]]:
    """Agrupa mencoes. Retorna entidades canonicas e o mapa (paper_id, nome) -> id canonico."""
    uf = _UF(len(mentions))
    by_key: dict[tuple[str, str], int] = {}
    for i, m in enumerate(mentions):
        for form in [m.name, *m.aliases]:
            # mesmo nome em tipos diferentes nao funde: serie Counter-Strike != jogo Counter-Strike
            k = (m.type, norm_key(form))
            if not k[1]:
                continue
            if k in by_key and compatible(m.name, mentions[by_key[k]].name):
                uf.union(i, by_key[k])
            else:
                by_key.setdefault(k, i)

    if embed is not None and len(mentions) > 1:
        groups = defaultdict(list)
        for i in range(len(mentions)):
            groups[uf.find(i)].append(i)
        reps = list(groups)
        vecs = embed([mentions[r].name for r in reps])
        for a in range(len(reps)):
            for b in range(a + 1, len(reps)):
                ma, mb = mentions[reps[a]], mentions[reps[b]]
                if ma.type != mb.type or digits(ma.name) != digits(mb.name):
                    continue
                sim = sum(x * y for x, y in zip(vecs[a], vecs[b]))
                # embedding sozinho funde nomes curtos diferentes (Leiden ~ Louvain): exige
                # tambem grafia parecida
                if sim >= threshold and lexical_sim(ma.name, mb.name) >= 0.85:
                    uf.union(reps[a], reps[b])

    clusters = defaultdict(list)
    for i in range(len(mentions)):
        clusters[uf.find(i)].append(i)

    canon: list[Canonical] = []
    mapping: dict[tuple[str, str], str] = {}
    used_ids: set[str] = set()
    # quem aparece em mais artigos fica com o id curto quando dois nomes colidem
    for idxs in sorted(clusters.values(), key=lambda ix: -len({mentions[i].doc_id for i in ix})):
        ms = [mentions[i] for i in idxs]
        name = Counter(m.name for m in ms).most_common(1)[0][0]
        etype = Counter(m.type for m in ms).most_common(1)[0][0]
        cid = slug(name)
        while cid in used_ids:  # nomes iguais de tipos diferentes mal resolvidos
            cid += "-" + etype.lower()
        used_ids.add(cid)
        forms = sorted({m.name for m in ms} | {a for m in ms for a in m.aliases} - {name})
        desc = max((m.description for m in ms), key=len, default="")
        canon.append(Canonical(cid, name, etype, forms, desc,
                               sorted({m.doc_id for m in ms}), sorted({m.name for m in ms})))
        for m in ms:
            mapping[(m.doc_id, m.name)] = cid
    return canon, mapping
