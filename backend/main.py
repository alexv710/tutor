from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import datetime
import openai
import subprocess
from contextlib import asynccontextmanager
import os
import tempfile
from supabase import create_client, Client
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Configuration settings are obtained from environment variables
    openai_api_key: str
    supabase_email: str
    supabase_password: str
    supabase_url: str
    supabase_key: str
    lesson_plans_dir: str
    ENVIRONMENT: str  # Use 'dev' for development mode to avoid using OpenAI API unnecessarily

    class Config:
        env_file = ".env"


settings = Settings()

# Initialize the Supabase client and authenticate
supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
auth_response = supabase.auth.sign_in_with_password(
    {"email": settings.supabase_email, "password": settings.supabase_password}
)
# TODO: Handle the authentication response properly.

# Set the OpenAI API key
openai.api_key = settings.openai_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup code would go here.
    yield
    # Clean up logic, such as logging out from services, can be placed here.
    supabase.auth.sign_out()


app = FastAPI(lifespan=lifespan)


class LessonPlan(BaseModel):
    title: str
    objectives: Optional[str] = None
    materials_needed: Optional[str] = None
    plan_details: Optional[str] = None


@app.post("/generate-lesson-plan/")
async def generate_lesson_plan(lesson_plan: LessonPlan):
    # Build the message to send to the OpenAI API based on input
    user_message_content = f"Create a lesson plan titled '{lesson_plan.title}'."
    if lesson_plan.objectives:
        user_message_content += f" The objectives are: '{lesson_plan.objectives}'."
    if lesson_plan.materials_needed:
        user_message_content += f" Materials needed: '{lesson_plan.materials_needed}'."
    if lesson_plan.plan_details:
        user_message_content += f" Plan details: '{lesson_plan.plan_details}'."

    # Use development data or call the OpenAI API depending on the environment setting
    try:
        if settings.ENVIRONMENT == "dev":
            # For development, read a local file instead of calling the OpenAI API
            with open(f"{settings.lesson_plans_dir}/lesson_plan_dev.tex", "r") as file:
                latex_content = file.read()
        else:
            # Call the OpenAI API to generate the lesson plan in LaTeX format
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Generate a LaTeX lesson plan."},
                    {"role": "user", "content": user_message_content},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            # TODO: Handle potential issues with the OpenAI response format.
            latex_content = response.choices[0].message["content"]

        # Save the generated LaTeX content to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tex") as temp_file:
            temp_file.write(latex_content.encode("utf-8"))
            temp_file_path = temp_file.name

        # Upload the temporary file to Supabase
        with open(temp_file_path, "rb") as file:
            tex_filename = (
                f"lesson_plan_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.tex"
            )
            upload_response = supabase.storage.from_("lesson_plans_tex").upload(
                tex_filename, file
            )
            # TODO: Check the upload_response to ensure the upload was successful.

        # Clean up: Remove the temporary file after uploading
        os.remove(temp_file_path)

        return {"latex": latex_content}
    except openai.error.OpenAIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compile-latex/")
async def compile_latex_endpoint(tex_filename: str):
    """
    Endpoint to compile a LaTeX file to a PDF.
    :param tex_filename: The filename of the LaTeX file in Supabase storage.
    :return: A JSON with the PDF filename or an error message.
    """
    # Step 1: Download the .tex file from Supabase
    tex_file_path = download_file_from_supabase(tex_filename)

    # TODO: Validate the downloaded content before proceeding to compile

    # Step 2: Compile the LaTeX file to PDF
    pdf_success, pdf_file_path = compile_latex_to_pdf(tex_file_path)

    if pdf_success:
        # Step 3: Upload the PDF file back to Supabase
        upload_pdf_to_supabase(pdf_file_path, tex_filename)

        # Best Practice: Use try/finally to ensure clean-up actions are always taken
        try:
            return {
                "message": "Successfully compiled LaTeX to PDF.",
                "pdf_filename": os.path.basename(
                    pdf_file_path
                ),  # Return just the filename
            }
        finally:
            # Clean up: Remove the local temporary files
            os.remove(tex_file_path)
            os.remove(pdf_file_path)
    else:
        # Clean up the local temporary .tex file in case of failure as well
        os.remove(tex_file_path)
        raise HTTPException(status_code=500, detail="Error compiling LaTeX to PDF.")


# Helper function to download .tex file from Supabase
def download_file_from_supabase(tex_filename: str) -> str:
    """
    Downloads a .tex file from Supabase storage to a local temporary file.

    :param tex_filename: The name of the .tex file to be downloaded.
    :return: The file path to the temporary local .tex file.
    """
    # TODO: Add input validation to sanitize the tex_filename parameter

    try:
        # Try to download the file from the Supabase bucket
        download_response = supabase.storage.from_("lesson_plans_tex").download(
            tex_filename
        )

        # TODO: Validate download_response to ensure the file was downloaded correctly

        # Create a temporary file to store the downloaded content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tex") as temp_file:
            temp_file.write(download_response)
            return temp_file.name
    except Exception as e:
        # TODO: Implement more granular exception handling
        raise HTTPException(status_code=500, detail=f"Failed to download the file: {e}")


def upload_pdf_to_supabase(pdf_file_path: str, tex_filename: str) -> dict:
    """
    Uploads a PDF file to Supabase storage, replacing the existing file if it exists.

    :param pdf_file_path: Path to the local PDF file to upload.
    :param tex_filename: The name of the original .tex file (used to determine the PDF filename).
    :return: A dictionary containing the status and data of the upload operation.
    """
    try:
        pdf_filename = tex_filename.replace(".tex", ".pdf")
        bucket_name = "lesson_plans"  # Replace with the actual bucket name

        # Open and read the content of the PDF file to upload
        with open(pdf_file_path, "rb") as pdf_file:
            pdf_content = pdf_file.read()

        # Define the upload options
        file_options = {
            "content-type": "application/pdf",
            "cache-control": "public, max-age=31536000",  # 1 year
            "x-upsert": "true",
        }

        # Upload the file to Supabase
        upload_response = supabase.storage.from_(bucket_name).upload(
            pdf_filename, pdf_content, file_options=file_options
        )

        # TODO: Check the upload response to confirm successful upload

        return {"status": "success", "data": upload_response}
    except Exception as e:
        # Log the error for debugging
        return {"status": "error", "data": str(e)}


def compile_latex_to_pdf(tex_file_path: str) -> (bool, str):
    """
    Compiles a LaTeX file into a PDF using a Docker container.

    :param tex_file_path: The local path to the .tex file.
    :return: A tuple containing a boolean indicating success, and the path to the generated PDF file.
    """
    try:
        # Define the Docker command to run the compilation
        current_uid = os.getuid()
        current_gid = os.getgid()
        docker_command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{os.path.dirname(tex_file_path)}:/data",
            "-u",
            f"{current_uid}:{current_gid}",
            "blang/latex:ctanfull",
            "pdflatex",
            "-interaction=nonstopmode",
            f"/data/{os.path.basename(tex_file_path)}",
        ]

        # Execute the Docker command
        result = subprocess.run(
            docker_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # The path to the expected output PDF file
        pdf_file_path = tex_file_path.replace(".tex", ".pdf")

        # Return True if compilation was successful (return code 0), along with the PDF file path
        return result.returncode == 0, pdf_file_path
    except Exception as e:
        # Log the error for debugging
        return False, e


# Health check endpoint
@app.get("/health/")
async def health_check():
    return {"status": "healthy"}
