import streamlit as st
import pandas as pd
import os
from datetime import datetime
import io
from fpdf import FPDF

FILE_NAME = "inspecao_detectores.xlsx"
DETECTORES = ["Detector-Patrimônio-1998", "Detector-Patrimônio-1997", "Detector-Patrimônio-1996", "Detector-Patrimônio-1881", "Detector-Patrimônio-1882"]
LOCALIDADES = ["Lab. Proteômica", "Lab. Microbiologia", "Lab. Geral", "Sala PacBio", "Sala de nitrogênio líquido"]
PERIODOS = ["Entrada", "Saída"]
MODELO = "Y-BZ:XT-XWHM-Y-BZ"
FABRICANTE = "Gasalert"

def load_data():
    if os.path.exists(FILE_NAME):
        return pd.read_excel(FILE_NAME)
    else:
        return pd.DataFrame(columns=[
            "Data", "Período", "Detector", "Localidade",
            "Alarme Sonoro", "Alarme Luminoso", "Ambiente Liberado",
            "Técnico Responsável", "Matrícula", "Horário", "Modelo", "Fabricante", "Observações"
        ])

def save_data(df):
    df.to_excel(FILE_NAME, index=False, engine="openpyxl")

def gerar_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", style='B', size=14)

    # Cabeçalho principal
    pdf.cell(0, 10, "Check List para Inspeção Diária de Detectores de Gases", 0, 1, 'C')
    pdf.ln(5)

    if df.empty:
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, "Nenhum dado disponível para exibição.", 0, 1)
    else:
        grouped = df.groupby(["Data", "Detector"])
        for (data, detector), group in grouped:
            pdf.set_font("Arial", style='B', size=12)
            pdf.cell(0, 10, f"Detector: {detector} - Data: {data}", 0, 1)
            pdf.cell(0, 10, f"Modelo: {MODELO} - Fabricante: {FABRICANTE}", 0, 1)
            pdf.ln(5)

            # Cabeçalho das tabelas
            pdf.set_font("Arial", style='B', size=10)
            pdf.set_fill_color(200, 200, 255)  # Azul claro
            pdf.cell(95, 8, "Entrada", 1, 0, 'C', fill=True)
            pdf.set_fill_color(200, 255, 200)  # Verde claro
            pdf.cell(95, 8, "Saída", 1, 1, 'C', fill=True)

            entrada = group[group["Período"] == "Entrada"]
            saida = group[group["Período"] == "Saída"]
            max_rows = max(len(entrada), len(saida))

            for i in range(max_rows):
                pdf.set_font("Arial", size=9)

                texto_entrada = (
                    f"Téc: {entrada.iloc[i]['Técnico Responsável']} | Horário: {entrada.iloc[i]['Horário']}\n"
                    f"Alarme Sonoro: {entrada.iloc[i]['Alarme Sonoro']} | Alarme Luminoso: {entrada.iloc[i]['Alarme Luminoso']}\n"
                    f"Ambiente Liberado: {entrada.iloc[i]['Ambiente Liberado']} | Obs: {entrada.iloc[i]['Observações']}"
                ) if i < len(entrada) else ""

                texto_saida = (
                    f"Téc: {saida.iloc[i]['Técnico Responsável']} | Horário: {saida.iloc[i]['Horário']}\n"
                    f"Alarme Sonoro: {saida.iloc[i]['Alarme Sonoro']} | Alarme Luminoso: {saida.iloc[i]['Alarme Luminoso']}\n"
                    f"Ambiente Liberado: {saida.iloc[i]['Ambiente Liberado']} | Obs: {saida.iloc[i]['Observações']}"
                ) if i < len(saida) else ""

                # Calcula a altura máxima entre as duas células
                altura_maxima = max(
                    pdf.get_string_width(texto_entrada) // 95 * 6 + 6,
                    pdf.get_string_width(texto_saida) // 95 * 6 + 6
                )

                # Coluna Entrada com cor de fundo azul claro
                pdf.set_fill_color(230, 230, 255)  # Azul bem claro
                pdf.multi_cell(95, 6, texto_entrada, border=1, align='L', fill=True)
                y_atual = pdf.get_y() - altura_maxima

                # Coluna Saída com cor de fundo verde claro
                pdf.set_y(y_atual)
                pdf.set_x(105)
                pdf.set_fill_color(230, 255, 230)  # Verde bem claro
                pdf.multi_cell(95, 6, texto_saida, border=1, align='L', fill=True)

            pdf.ln(5)

    pdf_output = pdf.output(dest='S')
    return io.BytesIO(pdf_output)


def _render_multiline_table(pdf, group, fill_color):
    pdf.set_font("Arial", size=8)
    for _, row in group.iterrows():
        text = (
            f"Téc: {row['Técnico Responsável']} | Horário: {row['Horário']} | "
            f"Alarme Sonoro: {row['Alarme Sonoro']} | Alarme Luminoso: {row['Alarme Luminoso']} | "
            f"Ambiente Liberado: {row['Ambiente Liberado']} | Obs: {row['Observações']}"
        )
        # Ajusta a altura e aplica a cor de fundo
        pdf.set_fill_color(*fill_color)
        pdf.multi_cell(190, 5, text, border=1, align='L', fill=True)
        pdf.ln(1)


inspecoes = load_data()

st.title("Gerenciamento de Inspeção de Detectores de Gás")

data_selecionada = st.date_input("Selecione a data:", datetime.now().date())
detector = st.selectbox("Selecione o Detector:", DETECTORES)
localidade = st.selectbox("Selecione a Localidade:", LOCALIDADES)
periodo_selecionado = st.radio("Selecione o Período:", PERIODOS)

alarme_sonoro = st.radio("Alarme Sonoro:", ["Sim", "Não"])
alarme_luminoso = st.radio("Alarme Luminoso:", ["Sim", "Não"])
ambiente_liberado = st.radio("Ambiente Liberado para Trabalho:", ["Sim", "Não"])
tecnico_responsavel = st.text_input("Técnico Responsável:")
matricula = st.text_input("Matrícula:")
horario = st.text_input("Horário:")
observacoes = st.text_area("Observações:")
modelo = st.radio("Modelo:", [MODELO])
fabricante = st.radio("Fabricante:", [FABRICANTE])

if st.button("Registrar Inspeção"):
    if tecnico_responsavel.strip() == "" or matricula.strip() == "":
        st.warning("Por favor, preencha o nome do técnico responsável e a matrícula.")
    else:
        nova_inspecao = {
            "Data": data_selecionada.strftime('%Y-%m-%d'),
            "Período": periodo_selecionado,
            "Detector": detector,
            "Localidade": localidade,
            "Alarme Sonoro": alarme_sonoro,
            "Alarme Luminoso": alarme_luminoso,
            "Ambiente Liberado": ambiente_liberado,
            "Técnico Responsável": tecnico_responsavel,
            "Matrícula": matricula,
            "Horário": horario,
            "Modelo": modelo,
            "Fabricante": fabricante,
            "Observações": observacoes
        }
        inspecoes = pd.concat([inspecoes, pd.DataFrame([nova_inspecao])], ignore_index=True)
        save_data(inspecoes)
        st.success("Inspeção registrada com sucesso!")

st.subheader("Inspeções Registradas")
st.dataframe(inspecoes)

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    inspecoes.to_excel(writer, index=False)
output.seek(0)

st.download_button(
    label="Baixar Planilha de Inspeções",
    data=output,
    file_name="inspecao_detectores.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

if st.button("Gerar PDF"):
    pdf_file = gerar_pdf(inspecoes)
    st.download_button(
        label="Baixar PDF",
        data=pdf_file,
        file_name="checklist_inspecao.pdf",
        mime="application/pdf"
    )
