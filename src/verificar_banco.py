import sys
import os

# Adiciona o diretório raiz ao path para podermos importar os módulos do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.models import Base
from modules.core import engine
from sqlalchemy import inspect

def run():
    print("=========================================")
    print("INICIANDO VERIFICAÇÃO DO BANCO DE DADOS")
    print("=========================================")
    
    # 1. Inspecionar tabelas existentes antes da sincronização
    try:
        inspector = inspect(engine)
        tabelas_iniciais = inspector.get_table_names()
        print(f"[*] Tabelas atualmente existentes no banco: {tabelas_iniciais}")
    except Exception as e:
        print(f"[!] Erro ao conectar ao banco de dados: {e}")
        return

    # 2. Criar tabelas declaradas que ainda não existirem
    print("\n[*] Sincronizando e criando tabelas declaradas no SQLAlchemy...")
    try:
        # Cria todas as tabelas (historico_execucoes, metadados_imagens, etc.) se não existirem
        Base.metadata.create_all(bind=engine)
        print("[+] Sincronização executada com sucesso.")
    except Exception as e:
        print(f"[!] Erro ao sincronizar/criar tabelas: {e}")
        return

    # 3. Listar tabelas após sincronização para validar
    try:
        inspector = inspect(engine)
        tabelas_finais = inspector.get_table_names()
        print(f"\n[*] Tabelas após verificação/sincronização: {tabelas_finais}")
        
        # Mostrar detalhes de cada tabela
        for tabela in tabelas_finais:
            print(f"\n--- Estrutura da Tabela '{tabela}' ---")
            colunas = inspector.get_columns(tabela)
            for col in colunas:
                print(f"  - Coluna: {col['name']} ({col['type']}) | Nullable: {col['nullable']}")
            
            constraints = inspector.get_unique_constraints(tabela)
            if constraints:
                print(f"  - Restrições de Unicidade:")
                for c in constraints:
                    print(f"    * Nome: {c['name']} | Colunas: {c['column_names']}")
                    
    except Exception as e:
        print(f"[!] Erro ao inspecionar tabelas finais: {e}")

    print("\n=========================================")
    print("FIM DA VERIFICAÇÃO DO BANCO DE DADOS")
    print("=========================================")

if __name__ == "__main__":
    run()
