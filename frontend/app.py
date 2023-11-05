import requests
import streamlit as st
from st_supabase_connection import SupabaseConnection
import tempfile
import os
from datetime import datetime

st.set_page_config(layout="wide")

# Initialize connection to Supabase.
st_supabase_client = st.connection(
    "supabase",
    type=SupabaseConnection,
    # URL and Key are expected to be provided as Streamlit Secrets for security reasons.
)

# Define the URL of the backend server and the Supabase storage bucket names
# from the Streamlit secrets store.
BACKEND_URL = st.secrets["backend"]["BACKEND_URL"]
BUCKET_NAME_TEX = st.secrets["supabase"]["BUCKET_NAME_TEX"]
BUCKET_NAME_PDF = st.secrets["supabase"]["BUCKET_NAME_PDF"]

# TODO: Implement proper session management, to handle user sessions more securely.
# Currently, we're storing the user in the session state directly after login, which
# may not be the most secure approach.


# Function to handle user sign-up.
def sign_up(email, password):
    user, error = st_supabase_client.auth.sign_up(dict(email=email, password=password))
    if error:
        st.error(f"Sign up failed: {error}")
    else:
        st.success(f"Sign up successful for {email}")


# Function to handle user login.
def log_in(email, password):
    user, error = st_supabase_client.auth.sign_in_with_password(
        dict(email=email, password=password)
    )
    if error:
        st.error(f"Login failed: {error}")
    else:
        st.session_state["user"] = user  # Store user in session state.
        st.success(f"Logged in as {email}")


# Function to handle user logout.
def log_out():
    error = st_supabase_client.auth.sign_out()
    if error:
        st.error(f"Logout failed: {error}")
    else:
        st.session_state.pop("user", None)  # Remove user from session state.
        st.success("Logged out successfully")
        st.experimental_rerun()  # Refresh the app to reflect logout.


# UI elements for Sign Up.
def show_sign_up():
    with st.form("Sign Up"):
        st.subheader("Sign Up")
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        sign_up_button = st.form_submit_button("Sign Up")

        if sign_up_button:
            sign_up(email, password)


# UI elements for Login.
def show_login():
    with st.form("Log In"):
        st.subheader("Log In")
        email = st.text_input("Email Address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        log_in_button = st.form_submit_button("Log In")

        if log_in_button:
            log_in(email, password)
            st.experimental_rerun()  # Rerun the app to refresh the session state.


# UI element for Logout.
def show_logout():
    if st.button("Log Out"):
        log_out()


# Helper function to list files in a bucket
def list_files_in_bucket(bucket_name, file_extension):
    response = st_supabase_client.client.storage.from_(bucket_name).list()

    # Assuming your list_objects call returns a list of dictionaries, each with a "name" key
    files = [obj["name"] for obj in response if obj["name"].endswith(file_extension)]
    if not files:
        st.warning(
            f"No files with extension '{file_extension}' found in the bucket '{bucket_name}'."
        )
    return files


# Function to display .tex files in the UI for selection and editing
def show_tex_files(bucket_name):
    st.header("TeX Files")

    # Retrieve the updated list of .tex files
    tex_files = list_files_in_bucket(bucket_name, ".tex")

    # Display the selectbox with the list of files
    # Use a session state key to store the current file selection
    if "selected_tex_file" not in st.session_state:
        st.session_state["selected_tex_file"] = None

    previous_selection = st.session_state["selected_tex_file"]
    selected_tex_file = st.selectbox(
        "Select a TeX file to edit:",
        tex_files,
        index=tex_files.index(previous_selection)
        if previous_selection in tex_files
        else 0,
    )

    # Check if the selected file has changed
    if selected_tex_file != previous_selection:
        # Update the session state with the new file selection
        st.session_state["selected_tex_file"] = selected_tex_file
        # Update the session state with a new timestamp to trigger a refresh
        st.session_state["last_file_refresh"] = datetime.now().timestamp()

    # When a file is selected, fetch and display its content
    # Only fetch the content if the file selection has changed
    if selected_tex_file and (
        previous_selection != selected_tex_file
        or "last_file_refresh" not in st.session_state
    ):
        # Fetch and display the file content
        file_content = get_tex_file_content(bucket_name, selected_tex_file)
        st.session_state["file_content"] = file_content

    elif "file_content" in st.session_state:
        file_content = st.session_state["file_content"]
    else:
        file_content = ""

    edited_content = st.text_area("Edit TeX Content:", value=file_content, height=1000)

    # Update the content of the .tex file
    if st.button(f"Save Changes to {selected_tex_file}"):
        if update_tex_file_content(
            bucket_name, selected_tex_file, edited_content.encode("utf-8")
        ):
            st.success(f"Successfully updated {selected_tex_file}")
        else:
            st.error(f"Failed to update {selected_tex_file}")

    # Generate PDF from .tex file
    if st.button(f"Generate PDF from {selected_tex_file}"):
        # Here you would replace with the actual URL of your backend server
        compile_endpoint = f"{BACKEND_URL}/compile-latex/"
        response = requests.post(f"{compile_endpoint}?tex_filename={selected_tex_file}")

        if response.ok:
            st.success(f"Successfully generated PDF for {selected_tex_file}")
            # Here you would handle the response, for example by downloading the PDF
            # or providing a link to where the PDF can be viewed/downloaded
        else:
            st.error(f"Failed to generate PDF for {selected_tex_file}: {response.text}")


def get_tex_file_content(bucket_name, file_name):
    """
    Fetches the content of a TeX file from a specified Supabase storage bucket.

    Args:
        bucket_name (str): The name of the Supabase storage bucket.
        file_name (str): The name of the file to fetch.

    Returns:
        str: The content of the file as a string, or an empty string if an error occurs.
    """
    # Attempt to download the file from the bucket
    response = st_supabase_client.client.storage.from_(bucket_name).download(file_name)

    # Unpack the response tuple
    content = response.decode("UTF-8")

    # Return the decoded content
    return content


def update_tex_file_content(bucket_name: str, file_name: str, content: bytes) -> dict:
    """
    Uploads or updates a .tex file in the specified Supabase Storage bucket.

    Parameters:
    - bucket_name: The name of the Supabase Storage bucket.
    - file_name: The name of the .tex file to upload/update.
    - content: The new content for the .tex file in bytes.

    Returns:
    - A dictionary with the response from the Supabase Storage API.
    """
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        # Write the content to the temporary file
        tmp_file.write(content)
        # Make sure all data is flushed to the file
        tmp_file.flush()
        # Get the temporary file name
        temp_file_path = tmp_file.name

    # Upload the file
    try:
        file_options = {
            "content-type": "text/plain",
            "x-upsert": "true",
        }
        with open(temp_file_path, "rb") as f:
            response = st_supabase_client.client.storage.from_(bucket_name).upload(
                path=file_name, file=f, file_options=file_options
            )
    finally:
        # Remove the temporary file
        os.remove(temp_file_path)

    # Return the response from the Supabase API
    return response


# Assuming you have a function to create a signed URL for the file
def generate_signed_url(bucket_name: str, file_name: str):
    """Generate a signed URL to access a file in a Supabase bucket."""
    url = st_supabase_client.create_signed_urls(
        bucket_name, [file_name], 60
    )  # URL valid for 60 seconds
    return url.url


# Function to display .pdf files in the main area for viewing
def show_pdf_files(bucket_name):
    st.header("PDF Files")

    # Ensure that 'refresh_counter' is initialized in the session state
    if "refresh_counter" not in st.session_state:
        st.session_state["refresh_counter"] = 0

    # Button to refresh the list of files
    if st.button("Refresh list of PDF files"):
        st.session_state["refresh_counter"] += 1

    # Pass the current value of the counter to the function
    pdf_files = list_files_in_bucket(bucket_name, ".pdf")

    selected_pdf_file = st.selectbox("Select a PDF file to view:", pdf_files)

    if selected_pdf_file:
        try:
            response = st_supabase_client.client.storage.from_(
                bucket_name
            ).create_signed_url(selected_pdf_file, 60)

            if "signedURL" in response:
                signed_url = response["signedURL"]
                st.success("Signed URL generated successfully.")
                # Embed the PDF in an iframe to display it in the Streamlit app
                st.markdown(
                    f'<iframe src="{signed_url}" width="700" height="1000" type="application/pdf"></iframe>',
                    unsafe_allow_html=True,
                )
            else:
                st.error("Failed to generate a signed URL for the PDF.")

        except Exception as e:
            st.error(f"An error occurred: {e}")


# Function to send the lesson plan data to the backend
def send_lesson_plan_to_backend(lesson_plan):
    response = requests.post(f"{BACKEND_URL}/generate-lesson-plan/", json=lesson_plan)
    if response.status_code == 200:
        st.success("Lesson plan created successfully!")
        # Handle the response as needed, e.g., display a message, redirect, etc.
    else:
        st.error("An error occurred while creating the lesson plan.")


# Function to render the form for lesson plan creation
def create_lesson_plan_form():
    with st.expander("Create New Lesson Plan"):
        with st.form(key="lesson_plan_form"):
            st.subheader("Create a New Lesson Plan")
            title = st.text_input("Lesson Title", key="title")
            objectives = st.text_area("Lesson Objectives", key="objectives")
            materials_needed = st.text_area("Materials Needed", key="materials_needed")
            plan_details = st.text_area("Lesson Plan Details", key="plan_details")
            submit_button = st.form_submit_button(label="Create Lesson Plan")

            if submit_button:
                lesson_plan_data = {
                    "title": title,
                    "objectives": objectives,
                    "materials_needed": materials_needed,
                    "plan_details": plan_details,
                }
                send_lesson_plan_to_backend(lesson_plan_data)


# Main app
def main():
    st.title("Lesson Plan Generator")

    # If user is not logged in, show login and sign up forms
    if st_supabase_client.auth.get_user() is None:
        show_login()
        show_sign_up()

    else:
        st.write(f"Logged in as {st_supabase_client.auth.get_user().user.email}")

        show_logout()

        # Render the lesson plan creation form
        create_lesson_plan_form()

        col1, col2 = st.columns(2)

        # Show .tex and .pdf files for management
        with col1:
            show_tex_files(BUCKET_NAME_TEX)

        with col2:
            show_pdf_files(BUCKET_NAME_PDF)


# Run the main app
if __name__ == "__main__":
    main()
