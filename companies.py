"""
Universo do dossiê. Começa só com a RDOR; expandir é adicionar uma entrada aqui
(e fatiar os dados da empresa em data/). O dashboard é parametrizado por ticker.
"""

COMPANIES = {
    "RDOR3": {
        "nome": "Rede D'Or São Luiz",
        "setor": "Saúde · Hospitais",
        "cnpj": "06.047.087/0001-39",
    },
    "PRIO3": {
        "nome": "PRIO S.A.",
        "setor": "Petróleo & Gás · E&P",
        "cnpj": "10.629.105/0001-68",
    },
    "VALE3": {
        "nome": "Vale S.A.",
        "setor": "Mineração · Minério de ferro",
        "cnpj": "33.592.510/0001-54",
    },
}

# Empresa em foco no v1 (a primeira da lista quando houver mais).
FOCO = "RDOR3"
