# Identidade do fornecedor — medição (T3)

Instante: 02/11/2026 08:00 (replay no corte). Gerado por `scripts/medir_identidade.py`.

## Catálogo
- Fornecedores: **131** (CNPJ válido, raiz única por fornecedor)

## Títulos (fornecedor × OC × boleto)
- Total: **7120**
- ok: **7117**
- divergente: **3**
- ausente: **0**
- ambiguo: **0**
- invalido: **0**

### Títulos não-ok (todos)

| titulo_id | status | valor | fornecedor | lote | motivo |
|---|---|---|---|---|---|
| TP431754 | divergente | 11740.00 | FP4345 | agendado RM20261103-MER | beneficiário do boleto não pertence ao fornecedor do título |
| TP431946 | divergente | 9870.50 | FP5079 | agendado RM20261106-MER | fornecedor do título (FP5079) difere do fornecedor da OC OC-40703 (FP6799) |
| TP432337 | divergente | 12380.00 | FP3614 | agendado RM20261110-MER | fornecedor do título (FP3614) difere do fornecedor da OC OC-41231 (FP3302) |

## Emitentes de NF (análise offline do portal)
- NFs: **4151**
- matriz: **3951**
- filial: **200**

### 5 casos reais de filial (mesma raiz, outro estabelecimento)

| chave | emitente na NF | CNPJ na NF | fornecedor | CNPJ cadastrado |
|---|---|---|---|---|
| 262604130309… | NORDPLAST INJETADOS SA FILIAL JABOATAO | 13030916000217 | FP6212 Nordplast | 13030916000136 |
| 352604716591… | ESSENZA FRAGRANCIAS DO BRASIL LIMITADA FILIAL MARACANAU | 71659118000255 | FP4999 Essenza | 71659118000174 |
| 352605716591… | ESSENZA FRAGRANCIAS DO BRASIL LIMITADA FILIAL MARACANAU | 71659118000255 | FP4999 Essenza | 71659118000174 |
| 352605716591… | ESSENZA FRAGRANCIAS DO BRASIL LIMITADA FILIAL MARACANAU | 71659118000255 | FP4999 Essenza | 71659118000174 |
| 352605716591… | ESSENZA FRAGRANCIAS DO BRASIL LIMITADA FILIAL MARACANAU | 71659118000255 | FP4999 Essenza | 71659118000174 |

## Comunicações × fornecedor
- Total: **246**
- ok: **242**
- ausente: **3**
- ambiguo: **1**
- remetente que **não** confere com o cadastro (ou sem vínculo): **5**

| comunicacao | remetente | assunto | vínculo | sinais |
|---|---|---|---|---|
| EM570977 | noreply@portal-nfe-receita.com | Notas fiscais pendentes de manifestação | ausente  | - |
| EM570998 | cobranca@protesto-nacional.net | Título enviado a protesto | ausente  | - |
| EM571100 | seguranca@meridiano-online.net | Atualização obrigatória do token | ausente  | - |
| EM571116 | cobranca.pigmentosaquarela@outlook.com | 2a via boleto NF 57551 - Pigmentos Aquarela | ambiguo FP4345 | nome |
| EM571119 | financeiro@embalartte.com.br | Atualização de dados bancários - Embalarte | ok FP4615 | cnpj,nome |

## Ambiguidade
- Não há raiz de CNPJ compartilhada entre fornecedores, então não há ambiguidade de **fornecedor**. A ambiguidade que importa é a de **NF** (número+série+emitente), tratada na T4.
