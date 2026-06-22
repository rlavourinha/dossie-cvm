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
    "RENT3": {
        "nome": "Localiza Rent a Car",
        "setor": "Aluguel de carros · Mobilidade",
        "cnpj": "16.670.085/0001-55",
        # diário de tesouraria começa em 2019 -> programas que iniciam antes
        # (9º/2017 e 10º/2018) ficam "sem dado de execução", não 0%.
        "exec_desde": "2019-07-01",
    },
}

# Empresa em foco no v1 (a primeira da lista quando houver mais).
FOCO = "RDOR3"
