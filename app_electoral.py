import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import shapefile
import numpy as np
import os

# 1. Configuración de página
st.set_page_config(layout="wide", page_title="Simulador Santa Fe - Análisis Profesional")

# --- SISTEMA DE LOGIN ---
def check_password():
    """Devuelve True si el usuario introdujo la contraseña correcta."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        # Pantalla de Login
        st.markdown("### 🔐 Acceso Restringido")
        st.info("Este tablero contiene datos sensibles. Por favor, identifícate.")
        user_pass = st.text_input("Contraseña:", type="password")
        
        if st.button("Acceder"):
            if user_pass == "santafe2026": # <--- AQUÍ PUEDES CAMBIAR TU CONTRASEÑA
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
        return False
    return True

# --- SOLO SE EJECUTA SI LA CONTRASEÑA ES CORRECTA ---
if check_password():

    # CSS para evitar que los iframes dejen "márgenes fantasmas" abajo
    st.markdown("""<style>iframe {margin-bottom: 0px !important; padding-bottom: 0px !important;}</style>""", unsafe_allow_html=True)

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    @st.cache_data
    def cargar_datos():
        ruta_shp = os.path.join(BASE_DIR, "circuito_21", "circuito_21.shp")
        ruta_csv_circuitos = os.path.join(BASE_DIR, "inteligencia_circuitos_votos.csv")
        ruta_csv_locales = os.path.join(BASE_DIR, "inteligencia_locales_votos.csv")
        
        sf = shapefile.Reader(ruta_shp)
        gdf = gpd.GeoDataFrame.from_features(sf.__geo_interface__)
        gdf.columns = [c.lower().strip() for c in gdf.columns] 
        
        col_id_shp = next((c for c in gdf.columns if 'circ' in c), gdf.columns[0])
        gdf['circuito_id'] = gdf[col_id_shp].apply(lambda x: int(re.search(r'(\d+)', str(x)).group(1)) if re.search(r'(\d+)', str(x)) else None)
        
        df_res = pd.read_csv(ruta_csv_circuitos, sep=';')
        df_res['circuito_id'] = df_res['circuito'].astype(int)
        
        df_locales = pd.read_csv(ruta_csv_locales, sep=';')
        df_locales['circuito_id'] = df_locales['circuito'].astype(int)
        
        def limpiar_nombre(n):
            if pd.isna(n): return "S/N"
            res = re.sub(r"SANTA FE\s*\((.*?)\)", r"\1", str(n)).replace("SANTA FE", "").strip()
            return res if res else "S/N"
        df_res['nombre_limpio'] = df_res['nombre_circuito'].apply(limpiar_nombre)
        
        if 'cabecera' in gdf.columns:
            gdf['cabecera'] = gdf['cabecera'].astype(str).str.strip()
            gdf_sf = gdf[gdf['cabecera'] == 'Santa Fe'].copy()
        else:
            gdf_sf = gdf.copy()
        return gdf_sf, df_res, df_locales

    gdf_sf, df_res, df_locales = cargar_datos()

    partidos_base = ['UNIDOS PARA CAMBIAR SANTA FE', 'MÁS PARA SANTA FE', 'LA LIBERTAD AVANZA', 'SANTA FE EN COMUN', 'PROPUESTA FEDERAL', 'SOMOS VIDA Y LIBERTAD']

    # --- SIDEBAR: ALIANZAS ---
    st.sidebar.header("Gestión de Alianzas")
    num_alianzas = st.sidebar.slider("¿Cuántas alianzas simular?", 1, 3, 1)
    alianzas = {}
    usados = set()

    for i in range(num_alianzas):
        st.sidebar.markdown(f"---")
        nombre_al = st.sidebar.text_input(f"Nombre Alianza {i+1}:", f"ALIANZA {i+1}", key=f"al_nom_{i}")
        miembros = st.sidebar.multiselect(f"Partidos en {nombre_al}:", [p for p in partidos_base if p not in usados], key=f"al_part_{i}")
        if miembros:
            alianzas[nombre_al] = miembros
            for m in miembros: usados.add(m)

    def procesar_alianzas(df):
        temp_df = df.copy()
        for nom, mbs in alianzas.items():
            temp_df[nom] = temp_df[mbs].sum(axis=1)
        return temp_df

    df_sim = procesar_alianzas(df_res)
    df_locales_sim = procesar_alianzas(df_locales)
    competidores = [p for p in partidos_base if p not in usados] + list(alianzas.keys())

    # --- RANKING GENERAL ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Resultados Generales")
    v_partidos = df_sim[competidores].sum()
    v_blancos = df_sim['Blancos'].sum()
    v_nulos = df_sim['Nulos'].sum()
    t_validos_gen = v_partidos.sum() + v_blancos
    t_emitidos_gen = t_validos_gen + v_nulos

    ranking_gen = []
    for p in v_partidos.sort_values(ascending=False).index:
        vts = v_partidos[p]
        ranking_gen.append({'Lista': p, 'Votos': int(vts), '%': f"{(vts/t_validos_gen*100):.2f}%"})

    ranking_gen.append({'Lista': 'Blancos', 'Votos': int(v_blancos), '%': f"{(v_blancos/t_validos_gen*100):.2f}%"})
    ranking_gen.append({'Lista': 'Nulos', 'Votos': int(v_nulos), '%': f"{(v_nulos/t_emitidos_gen*100):.2f}%"})

    st.sidebar.table(pd.DataFrame(ranking_gen).set_index('Lista'))

    # --- INTERFAZ PRINCIPAL ---
    st.title("🗳️ Tablero de Inteligencia: Santa Fe Ciudad")
    st.info("💡 **Haz clic en un circuito para ver locales. Las tablas aparecerán debajo.**")

    c1, c2 = st.columns(2)
    with c1: ver_puesto = st.radio("Criterio del mapa:", ["1º puesto", "2º puesto"], horizontal=True)
    with c2: estilo = st.radio("Visualización:", ["Color Sólido", "Intensidad por %"], horizontal=True)

    def calc_oficial(row, n):
        orden = row[competidores].sort_values(ascending=False)
        tv = row[competidores].sum() + row['Blancos']
        te = tv + row['Nulos']
        p_nom = orden.index[n-1] if n-1 < len(orden) else "N/A"
        p_vts = orden.values[n-1] if n-1 < len(orden) else 0
        p_pct = (p_vts / tv * 100) if tv > 0 else 0
        return p_nom, p_vts, p_pct, tv, te

    p_idx = 1 if "1º" in ver_puesto else 2
    df_sim['Show_Part'], df_sim['Show_Vts'], df_sim['Show_Pct'], df_sim['TV'], df_sim['TE'] = zip(*df_sim.apply(lambda r: calc_oficial(r, p_idx), axis=1))

    color_map = {'UNIDOS PARA CAMBIAR SANTA FE': "#db9e34", 'LA LIBERTAD AVANZA': '#9b59b6', 'MÁS PARA SANTA FE': "#49d5e7", 'SANTA FE EN COMUN': "#09c4e4", 'PROPUESTA FEDERAL': '#f1c40f', 'SOMOS VIDA Y LIBERTAD': '#e74c3c'}
    for i, al in enumerate(alianzas.keys()): color_map[al] = ["#1a9ebc", '#d35400', '#2c3e50'][i % 3]

    mapa_final = gdf_sf.merge(df_sim, on='circuito_id')

    def crear_html(row):
        r_local = row[competidores].sort_values(ascending=False)
        html = f"<b>{row['nombre_limpio']}</b><br><table style='font-size:10px;'>"
        for i, (part, vts) in enumerate(r_local.items()):
            pct = (vts / row['TV'] * 100)
            neg = "font-weight:bold;color:red;" if i+1 == p_idx else ""
            html += f"<tr style='{neg}'><td>{i+1}º</td><td>{part[:12]}</td><td>{pct:.1f}%</td></tr>"
        
        html += f"<tr><td>Blancos</td><td>{(row['Blancos']/row['TV']*100):.1f}%</td></tr>"
        html += f"<tr><td>Nulos</td><td>{(row['Nulos']/row['TE']*100):.1f}%</td></tr>"
        
        return html + "</table>"

    mapa_final['tooltip_html'] = mapa_final.apply(crear_html, axis=1)

    # --- CONTENEDORES RÍGIDOS ---
    map_container = st.container()
    table_container = st.container()

    with map_container:
        m = folium.Map(location=[-31.6333, -60.7], zoom_start=13, tiles='cartodbpositron')

        folium.GeoJson(
            mapa_final.to_json(),
            style_function=lambda x: {
                'fillColor': color_map.get(x['properties']['Show_Part'], '#cccccc'),
                'color': 'white', 'weight': 1,
                'fillOpacity': np.clip((x['properties']['Show_Pct'] - 15) / 35, 0.2, 0.9) if estilo == "Intensidad por %" else 0.8
            },
            tooltip=folium.GeoJsonTooltip(fields=['tooltip_html'], labels=False)
        ).add_to(m)

        salida_mapa = st_folium(
            m, 
            use_container_width=True, 
            height=800, 
            key="mapa_final_sf", 
            returned_objects=["last_active_drawing"] 
        )

    # --- PROCESAR CLIC ---
    if salida_mapa and salida_mapa.get('last_active_drawing'):
        props = salida_mapa['last_active_drawing'].get('properties')
        if props and 'circuito_id' in props:
            new_id = int(props['circuito_id'])
            if st.session_state.get('sel_cir') != new_id:
                st.session_state['sel_cir'] = new_id
                st.rerun()

    # --- MOSTRAR TABLAS ---
    with table_container:
        if 'sel_cir' in st.session_state:
            id_s = st.session_state['sel_cir']
            info_c = df_sim[df_sim['circuito_id'] == id_s]
            
            if not info_c.empty:
                st.write("---")
                st.subheader(f"📍 Locales en {info_c['nombre_limpio'].values[0]} (Circuito {id_s})")
                
                if st.button("Cerrar detalle"):
                    del st.session_state['sel_cir']
                    st.rerun()

                locs = df_locales_sim[df_locales_sim['circuito_id'] == id_s]
                
                if not locs.empty:
                    cols = st.columns(3)
                    for i, (_, local) in enumerate(locs.iterrows()):
                        with cols[i % 3]:
                            st.markdown(f"**{local['establecimiento']}**<br><small>{local['domicilio']}</small>", unsafe_allow_html=True)
                            tv_l = local[competidores].sum() + local['Blancos']
                            te_l = tv_l + local['Nulos']
                            res_l = []
                            for p in local[competidores].sort_values(ascending=False).index:
                                res_l.append({'Partido': p, 'Votos': int(local[p]), '%': f"{(local[p]/tv_l*100 if tv_l >0 else 0):.2f}%"})
                            
                            res_l.append({'Partido': 'Blancos', 'Votos': int(local['Blancos']), '%': f"{(local['Blancos']/tv_l*100 if tv_l >0 else 0):.2f}%"})
                            res_l.append({'Partido': 'Nulos', 'Votos': int(local['Nulos']), '%': f"{(local['Nulos']/te_l*100 if te_l >0 else 0):.2f}%"})
                            
                            st.table(pd.DataFrame(res_l).set_index('Partido'))