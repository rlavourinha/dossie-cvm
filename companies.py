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
}

# Empresa em foco no v1 (a primeira da lista quando houver mais).
FOCO = "RDOR3"
