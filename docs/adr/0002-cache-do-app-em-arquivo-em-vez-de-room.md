# O app guarda a última resposta de cada tela em arquivo, não em Room

O app só precisa da última resposta de cada rota para mostrar dados com a rede fora do ar, então guarda cada uma como um arquivo, com escrita atômica. Room traria SQLite, KSP e migrações sem ganho para esse uso.
