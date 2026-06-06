Satellitum

Sistema de Processamento e Armazenamento de Dados Orbitais

Centro de Tecnologia

Programa de Pós-Graduação em Recursos Hídricos e Saneamento

Versão: Dev.06-2026

Antes de operar com o GEE é necessário obter um token de autenticação: 

1. Instalação da API
Certifique-se de que a biblioteca Python do Earth Engine está instalada no seu ambiente:

pip install earthengine-api

2. Gerando as Credenciais (Terminal)

Abra o terminal e execute o utilitário de autenticação:

earthengine authenticate

O terminal exibirá uma URL. Copie e abra no seu navegador.

Faça login com a conta Google vinculada ao Earth Engine.

Permita os acessos solicitados.

Copie o código de autorização gerado.

Cole o código de volta no prompt do terminal e pressione Enter.

O token de acesso será salvo no caminho padrão: ~/.config/earthengine/credentials.