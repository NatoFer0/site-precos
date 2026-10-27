from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import pandas as pd
import numpy as np
from pathlib import Path

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
DATA_DIR = Path(__file__).parent / "data"
MESES_ORDEM = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

def converter_para_numero(valor):
    if pd.isna(valor) or valor == "Falta" or str(valor).strip() == "":
        return np.nan
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace('R$', '').replace(' ', '')
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return np.nan

def carregar_planilha(ano: int):
    arquivo = DATA_DIR / f"precos_{ano}.xlsx"
    if not arquivo.exists():
        return None
    try:
        df = pd.read_excel(arquivo)
        df.columns = df.columns.str.strip()
        if 'Produto' in df.columns:
            df['Produto'] = df['Produto'].fillna("")
        for col in df.columns:
            if col != 'Produto':
                df[col] = df[col].apply(converter_para_numero)
        return df
    except Exception as e:
        return None

# ==========================================
# --- ROTAS DE PÁGINAS HTML ---
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/tabela/{ano}", response_class=HTMLResponse)
async def tela_tabela(request: Request, ano: int):
    return templates.TemplateResponse(request=request, name="tabela.html", context={"ano_atual": ano})

@app.get("/cesta/{ano}/{mes}", response_class=HTMLResponse)
async def tela_cesta(request: Request, ano: int, mes: str):
    return templates.TemplateResponse(request=request, name="cesta.html", context={"ano_atual": ano, "mes_atual": mes})

@app.get("/estatisticas/{ano}/{produto}", response_class=HTMLResponse)
async def tela_estatisticas(request: Request, ano: int, produto: str):
    return templates.TemplateResponse(request=request, name="estatisticas.html")

@app.get("/ranking/{ano}", response_class=HTMLResponse)
async def tela_ranking(request: Request, ano: int):
    return templates.TemplateResponse(request=request, name="ranking.html")

@app.get("/comparar/{ano}", response_class=HTMLResponse)
async def tela_comparar(request: Request, ano: int):
    return templates.TemplateResponse(request=request, name="comparar.html", context={"ano_atual": ano})

# ==========================================
# --- ROTAS DE API (DADOS) ---
# ==========================================

@app.get("/api/anos")
def listar_anos():
    anos = []
    if DATA_DIR.exists():
        for arquivo in DATA_DIR.glob("precos_*.xlsx"):
            try:
                ano = int(arquivo.stem.split("_")[1])
                if ano not in anos:
                    anos.append(ano)
            except (IndexError, ValueError):
                continue
    return sorted(anos)

@app.get("/api/comparar-historico")
def get_comparar_historico(anos: str = "all", inicio: str = None, fim: str = None):
    anos_disponiveis = listar_anos()
    if anos == "all":
        anos_para_carregar = anos_disponiveis
    else:
        try:
            anos_para_carregar = [int(a) for a in anos.split(",") if int(a) in anos_disponiveis]
        except:
            anos_para_carregar = anos_disponiveis
            
    if not anos_para_carregar:
        anos_para_carregar = anos_disponiveis

    timeline_bruta = []
    for ano in sorted(anos_para_carregar):
        for mes in MESES_ORDEM:
            timeline_bruta.append(f"{mes}/{ano}")
            
    timeline = timeline_bruta
    if inicio and fim and inicio in timeline_bruta and fim in timeline_bruta:
        idx_inicio = timeline_bruta.index(inicio)
        idx_fim = timeline_bruta.index(fim)
        if idx_inicio <= idx_fim:
            timeline = timeline_bruta[idx_inicio:idx_fim+1]

    if not timeline:
        return {"timeline": [], "dados": {}}

    dados_por_produto = {}
    for ano in anos_para_carregar:
        df = carregar_planilha(ano)
        if df is None: continue
        
        for idx, row in df.iterrows():
            nome = str(row['Produto']).strip()
            if not nome: continue
            
            if nome not in dados_por_produto:
                dados_por_produto[nome] = {}
                
            for mes in MESES_ORDEM:
                preco = row.get(mes)
                if not pd.isna(preco):
                    dados_por_produto[nome][f"{mes}/{ano}"] = float(preco)

    resultado = {}
    for nome, precos in dados_por_produto.items():
        serie = [precos.get(label, None) for label in timeline]
        resultado[nome] = serie

    return {
        "timeline": timeline,
        "dados": resultado
    }

@app.get("/api/tabela/{ano}")
def get_tabela(ano: int):
    df = carregar_planilha(ano)
    if df is None: raise HTTPException(status_code=404, detail="Ano não encontrado.")
    df_exibicao = df.fillna("Falta")
    if "Unnamed: 0" in df_exibicao.columns:
        df_exibicao = df_exibicao.drop(columns=["Unnamed: 0"])
    dados_json = df_exibicao.to_dict(orient="records")
    return {"ano": ano, "dados": dados_json}

@app.get("/api/cesta/{ano}/{mes}")
def get_cesta_mes(ano: int, mes: str):
    df = carregar_planilha(ano)
    if df is None: raise HTTPException(status_code=404, detail="Ano não encontrado.")
    if mes not in MESES_ORDEM:
        raise HTTPException(status_code=400, detail="Mês inválido.")
        
    produtos_validos = []
    for idx, row in df.iterrows():
        nome = str(row['Produto']).strip()
        preco = row.get(mes)
        if nome and not pd.isna(preco):
            produtos_validos.append({"produto": nome, "preco": float(preco)})
            
    if not produtos_validos:
        return {"erro": "Nenhum produto registrado neste mês."}
        
    produtos_validos.sort(key=lambda x: x['preco'], reverse=True)
    total_cesta = sum(p['preco'] for p in produtos_validos)
    
    dados_grafico = []
    for p in produtos_validos:
        dados_grafico.append({
            "label": p['produto'],
            "preco": round(p['preco'], 2),
            "porcentagem": (p['preco'] / total_cesta) * 100
        })

    return {
        "mes": mes,
        "ano": ano,
        "total_cesta": round(total_cesta, 2),
        "qtd_produtos": len(produtos_validos),
        "dados": dados_grafico
    }

@app.get("/api/graficos-cesta/{ano}")
def get_graficos_cesta(ano: int):
    df = carregar_planilha(ano)
    if df is None: raise HTTPException(status_code=404, detail="Ano não encontrado.")
    
    grafico_valores = []
    grafico_inflacao = []
    
    soma_total_cesta = 0
    count_total_cesta = 0
    valores_totais_cesta = []

    mes_base = None
    media_base = 0
    for mes in MESES_ORDEM:
        valores_mes = df[mes].dropna()
        if not valores_mes.empty:
            mes_base = mes
            media_base = valores_mes.mean()
            break
            
    for mes in MESES_ORDEM:
        valores_mes = df[mes].dropna()
        if not valores_mes.empty:
            total_carrinho = float(valores_mes.sum())
            qtd_produtos = len(valores_mes)
            media_produto = total_carrinho / qtd_produtos
            
            grafico_valores.append({
                "mes": mes,
                "total": round(total_carrinho, 2),
                "media": round(media_produto, 2),
                "qtd": qtd_produtos
            })

            soma_total_cesta += total_carrinho
            count_total_cesta += 1
            valores_totais_cesta.append(total_carrinho)
            
            inflacao = 0
            if media_base > 0:
                inflacao = ((media_produto - media_base) / media_base) * 100
                
            grafico_inflacao.append({
                "mes": mes,
                "inflacao": inflacao
            })
        else:
            grafico_valores.append({"mes": mes, "total": None, "media": None, "qtd": 0})
            grafico_inflacao.append({"mes": mes, "inflacao": None})

    media_custo_total = (soma_total_cesta / count_total_cesta) if count_total_cesta > 0 else 0
    desvio_custo_total = float(np.std(valores_totais_cesta)) if valores_totais_cesta else 0

    valores_inflacao = [item['inflacao'] for item in grafico_inflacao if item['inflacao'] is not None]
    media_inflacao_geral = float(np.mean(valores_inflacao)) if valores_inflacao else 0
    dp_inflacao = float(np.std(valores_inflacao)) if valores_inflacao else 0

    return {
        "grafico_valores": grafico_valores,
        "grafico_inflacao": grafico_inflacao,
        "media_inflacao_geral": media_inflacao_geral,
        "dp_inflacao": dp_inflacao,
        "mes_base": mes_base,
        "media_custo_total": media_custo_total,
        "desvio_custo_total": desvio_custo_total
    }

@app.get("/api/estatisticas/{ano}/{produto}")
def get_estatisticas(ano: int, produto: str):
    df = carregar_planilha(ano)
    if df is None: raise HTTPException(status_code=404, detail="Ano não encontrado.")
    produto_row = df[df['Produto'].astype(str).str.contains(produto, case=False, na=False)]
    if produto_row.empty:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    
    valores_serie = produto_row.drop(columns=['Produto']).iloc[0]
    valores_validos = valores_serie.dropna()
    if valores_validos.empty:
        return {"produto": produto, "mensagem": "Sem dados de preço."}
    
    media = float(valores_validos.mean())
    mediana = float(valores_validos.median())
    minimo = float(valores_validos.min())
    maximo = float(valores_validos.max())
    
    moda_val = valores_validos.mode()
    moda = float(moda_val.iloc[0]) if not moda_val.empty else None
    moda_freq = int((valores_validos == moda).sum()) if moda else 0
    
    desvio_padrao = float(valores_validos.std())
    cv = (desvio_padrao / media) * 100 if media > 0 else 0
    
    if cv < 5: volatilidade = "Baixa"
    elif cv < 15: volatilidade = "Moderada"
    else: volatilidade = "Alta"

    def achar_mes(valor):
        cols = [col for col in MESES_ORDEM if col in valores_serie.index]
        for col in cols:
            if valores_serie[col] == valor:
                return col
        return ""
        
    mes_min = achar_mes(minimo)
    mes_max = achar_mes(maximo)
    
    meses_preenchidos = [m for m in MESES_ORDEM if m in valores_serie.index and not pd.isna(valores_serie[m])]
    ultimo_mes = meses_preenchidos[-1] if meses_preenchidos else "N/A"
    ultimo_preco = float(valores_serie[ultimo_mes]) if ultimo_mes != "N/A" else 0
    
    variacao_mom = 0
    if len(meses_preenchidos) >= 2:
        penultimo_mes = meses_preenchidos[-2]
        preco_anterior = valores_serie[penultimo_mes]
        variacao_mom = ((ultimo_preco - preco_anterior) / preco_anterior) * 100

    # --- NOVA LÓGICA DE TENDÊNCIA (MÉDIA MÓVEL) ---
    tendencia = "Estável"
    if len(meses_preenchidos) >= 6:
        # Pega os últimos 6 meses preenchidos
        ultimos6 = meses_preenchidos[-6:]
        
        # Separa em duas janelas de 3 meses
        janela_antiga = [valores_serie[m] for m in ultimos6[:3]]
        janela_recente = [valores_serie[m] for m in ultimos6[3:]]
        
        media_antiga = sum(janela_antiga) / 3
        media_recente = sum(janela_recente) / 3
        
        if media_recente > media_antiga:
            tendencia = "Alta"
        elif media_recente < media_antiga:
            tendencia = "Queda"
    elif len(meses_preenchidos) >= 3:
        # Fallback para quem tem entre 3 e 5 meses: compara o primeiro e o último
        if valores_serie[meses_preenchidos[-1]] > valores_serie[meses_preenchidos[0]]:
            tendencia = "Alta"
        elif valores_serie[meses_preenchidos[-1]] < valores_serie[meses_preenchidos[0]]:
            tendencia = "Queda"
    # ----------------------------------------------

    variacoes = []
    for idx, row in df.iterrows():
        vals = [row[m] for m in MESES_ORDEM if m in row.index and not pd.isna(row[m])]
        if len(vals) > 1:
            var = ((vals[-1] - vals[0]) / vals[0]) * 100
            variacoes.append({'produto': row['Produto'], 'variacao': var})
    
    df_var = pd.DataFrame(variacoes)
    media_cesta = float(df_var['variacao'].mean()) if not df_var.empty else 0
    df_var['abs_var'] = df_var['variacao'].abs()
    df_var_sorted = df_var.sort_values(by='abs_var', ascending=False)
    df_var_sorted['rank'] = range(1, len(df_var_sorted) + 1)
    
    posicao_ranking = 0
    for _, r in df_var_sorted.iterrows():
        if r['produto'] == produto or produto.lower() in str(r['produto']).lower():
            posicao_ranking = r['rank']
            break

    total_meses = len([m for m in MESES_ORDEM if m in valores_serie.index])
    preenchidos = len(meses_preenchidos)
    completude = (preenchidos / total_meses) * 100 if total_meses > 0 else 0

    return {
        "produto": produto, "ano": ano, "media": media, "mediana": mediana,
        "moda": moda, "moda_freq": moda_freq, "minimo": minimo, "mes_minimo": mes_min,
        "maximo": maximo, "mes_maximo": mes_max, "desvio_padrao": desvio_padrao,
        "volatilidade": volatilidade, "cv": cv,
        "variacao_percentual": ((maximo - minimo) / minimo) * 100,
        "amplitude_reais": (maximo - minimo), "economia_maxima": (maximo - minimo),
        "ultimo_preco": ultimo_preco, "ultimo_mes": ultimo_mes, "variacao_mom": variacao_mom,
        "tendencia": tendencia, "posicao_ranking": posicao_ranking,
        "total_produtos": len(df_var), "media_cesta": media_cesta,
        "completude": completude, "historico": valores_serie.fillna("Falta").to_dict(),
        "meses_ordem": MESES_ORDEM
    }

@app.get("/api/ranking/{ano}")
def get_ranking(ano: int):
    df = carregar_planilha(ano)
    if df is None: raise HTTPException(status_code=404, detail="Ano não encontrado.")
    resultados = []
    
    variacoes_cesta = []
    for idx, row in df.iterrows():
        vals = [row[m] for m in MESES_ORDEM if m in row.index and not pd.isna(row[m])]
        if len(vals) > 1:
            var = ((vals[-1] - vals[0]) / vals[0]) * 100
            variacoes_cesta.append(var)
    media_cesta = np.mean(variacoes_cesta) if variacoes_cesta else 0

    for idx, row in df.iterrows():
        nome = row['Produto']
        if not nome or str(nome).strip() == "": continue
        
        valores = row.drop(labels=['Produto']).dropna()
        if valores.empty: continue
        
        media = float(valores.mean())
        minimo = float(valores.min())
        maximo = float(valores.max())
        dp = float(valores.std()) if len(valores) > 1 else 0
        cv = (dp / media) * 100 if media > 0 else 0
        
        vol = "Baixa" if cv < 5 else ("Moderada" if cv < 15 else "Alta")
        
        meses_val = [m for m in MESES_ORDEM if m in row.index and not pd.isna(row[m])]
        var_total = 0
        if len(meses_val) > 1:
            var_total = ((row[meses_val[-1]] - row[meses_val[0]]) / row[meses_val[0]]) * 100

        completude = (len(valores) / 12) * 100

        resultados.append({
            "produto": str(nome).strip(),
            "ultimo_preco": float(row[meses_val[-1]]) if meses_val else 0,
            "media": media,
            "minimo": minimo,
            "maximo": maximo,
            "var_total": var_total,
            "volatilidade": vol,
            "cv": cv,
            "completude": completude
        })
        
    resultados.sort(key=lambda x: abs(x['var_total']), reverse=True)
    for i, r in enumerate(resultados):
        r['ranking'] = i + 1
        
    return resultados