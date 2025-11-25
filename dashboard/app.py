import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Job Application Manager", layout="wide")

DATA_FILE = "data/applications.csv"

st.title("Job Application Manager")

if os.path.exists(DATA_FILE):
    df = pd.read_csv(DATA_FILE)
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Applications", len(df))
    col2.metric("Pending", len(df[df['Status'] == 'Applied']))
    col3.metric("Interviews", len(df[df['Status'] == 'Interview']))

    # Data Table
    st.subheader("Application Log")
    edited_df = st.data_editor(df, num_rows="dynamic")

    if st.button("Save Changes"):
        edited_df.to_csv(DATA_FILE, index=False)
        st.success("Changes saved!")

else:
    st.info("No applications logged yet. Use the Chrome Extension to add some!")

st.sidebar.header("About")
st.sidebar.info("This dashboard tracks your job applications. Use the Chrome Extension to log new ones.")
