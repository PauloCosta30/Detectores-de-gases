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

    # Cabeçalho do PDF
    pdf.cell(0, 10, "Check List para Inspeção Diária de Detectores de Gases", 0, 1, 'C')
    pdf.ln(10)

    if df.empty:
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, "Nenhum dado disponível para exibição.", 0, 1)
    else:
        grouped = df.groupby(["Data", "Detector"])
        for (data, detector), group in grouped:
            pdf.set_font("Arial", style='B', size=12)
            pdf.cell(95, 10, f"Detector: {detector} - Data: {data}", 0, 0)
            pdf.set_font("Arial", size=12)
            pdf.cell(95, 10, f"Modelo: {MODELO} - Fabricante: {FABRICANTE}", 0, 1)
            pdf.ln(5)
            pdf.cell(95, 10, "Entrada", 1, 0, 'C')
            pdf.cell(95, 10, "Saída", 1, 1, 'C')

            entrada = group[group["Período"] == "Entrada"]
            saida = group[group["Período"] == "Saída"]
            max_rows = max(len(entrada), len(saida))
            
            for i in range(max_rows):
                pdf.set_font("Arial", size=10)
                if i < len(entrada):
                    row_entrada = entrada.iloc[i]
                    pdf.cell(95, 10, f"Alarme Sonoro: {row_entrada['Alarme Sonoro']}", 0, 0)
                    pdf.cell(95, 10, f"Alarme Luminoso: {row_entrada['Alarme Luminoso']}", 0, 1)
                    pdf.cell(95, 10, f"Ambiente Liberado: {row_entrada['Ambiente Liberado']}", 0, 0)
                    pdf.cell(95, 10, f"Técnico: {row_entrada['Técnico Responsável']}", 0, 1)
                    pdf.cell(95, 10, f"Matrícula: {row_entrada['Matrícula']}", 0, 0)
                    pdf.cell(95, 10, f"Horário: {row_entrada['Horário']}", 0, 1)
                    pdf.cell(95, 10, f"Observações: {row_entrada['Observações']}", 0, 1)
                else:
                    pdf.cell(95, 10, "", 0, 0)
                    pdf.cell(95, 10, "", 0, 1)

                if i < len(saida):
                    row_saida = saida.iloc[i]
                    pdf.cell(95, 10, f"Alarme Sonoro: {row_saida['Alarme Sonoro']}", 0, 0)
                    pdf.cell(95, 10, f"Alarme Luminoso: {row_saida['Alarme Luminoso']}", 0, 1)
                    pdf.cell(95, 10, f"Ambiente Liberado: {row_saida['Ambiente Liberado']}", 0, 0)
                    pdf.cell(95, 10, f"Técnico: {row_saida['Técnico Responsável']}", 0, 1)
                    pdf.cell(95, 10, f"Matrícula: {row_saida['Matrícula']}", 0, 0)
                    pdf.cell(95, 10, f"Horário: {row_saida['Horário']}", 0, 1)
                    pdf.cell(95, 10, f"Observações: {row_saida['Observações']}", 0, 1)
                else:
                    pdf.cell(95, 10, "", 0, 0)
                    pdf.cell(95, 10, "", 0, 1)
            pdf.ln(5)
    
    pdf_output = pdf.output(dest='S').encode('latin1')
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
