import sqlite3
import os

# Define o nome do arquivo do banco de dados
DATABASE = 'gestao_frota.db'


def criar_db():
    """
    Cria o banco de dados e as tabelas se não existirem.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Tabela Utilizadores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Utilizadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            nivel_acesso INTEGER NOT NULL
        )
    ''')

    # Tabela Veiculos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Veiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            matricula TEXT NOT NULL UNIQUE,
            data_revisao TEXT,
            data_inspecao TEXT,
            foto_veiculo TEXT
        )
    ''')

    # Tabela Voltas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Voltas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_motorista INTEGER,
            id_veiculo INTEGER,
            destino TEXT NOT NULL,
            data_hora_saida TEXT NOT NULL,
            kms_saida REAL NOT NULL,
            acompanhantes TEXT,
            fotos_saida TEXT,
            data_hora_chegada TEXT,
            kms_chegada REAL,
            status INTEGER NOT NULL,
            FOREIGN KEY(id_motorista) REFERENCES Utilizadores(id),
            FOREIGN KEY(id_veiculo) REFERENCES Veiculos(id)
        )
    ''')

    # Tabela Incidencias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Incidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_utilizador INTEGER,
            id_volta INTEGER,
            descricao TEXT NOT NULL,
            data_reporte TEXT NOT NULL,
            fotos_incidencia TEXT,
            status INTEGER NOT NULL,
            FOREIGN KEY(id_utilizador) REFERENCES Utilizadores(id),
            FOREIGN KEY(id_volta) REFERENCES Voltas(id)
        )
    ''')

    conn.commit()
    conn.close()

    # Cria a pasta para as fotos, se não existir
    if not os.path.exists('fotos'):
        os.makedirs('fotos')


if __name__ == '__main__':
    criar_db()
    print("Banco de dados 'gestao_frota.db' e tabelas criadas com sucesso!")
    # Adicionar aqui um administrador inicial para poder fazer o login
    # e criar outros utilizadores.