from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import datetime
import openai
import subprocess
from contextlib import asynccontextmanager
import os
import io
import tempfile
from supabase import create_client, Client


from pydantic_settings import BaseSettings

ENVIRONMENT = "dev"


class Settings(BaseSettings):
    openai_api_key: str
    supabase_email: str
    supabase_password: str
    supabase_url: str
    supabase_key: str
    lesson_plans_dir: str

    class Config:
        env_file = ".env"


settings = Settings()

supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
# Authenticate with Supabase
print({"email": settings.supabase_email, "password": settings.supabase_password})
auth_response = supabase.auth.sign_in_with_password(
    {"email": settings.supabase_email, "password": settings.supabase_password}
)

openai.api_key = settings.openai_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # Here the application runs

    # Sign out the user on shutdown otherwise a background process
    # blocks the shutdown of the server
    supabase.auth.sign_out()


app = FastAPI(lifespan=lifespan)


# Define your LessonPlan schema with optional fields except for the title
class LessonPlan(BaseModel):
    title: str
    objectives: Optional[str] = None
    materials_needed: Optional[str] = None
    plan_details: Optional[str] = None


# Directory where lesson plan files will be saved
os.makedirs(settings.lesson_plans_dir, exist_ok=True)  # Ensure the directory exists


@app.post("/generate-lesson-plan/")
async def generate_lesson_plan(lesson_plan: LessonPlan):
    # Construct the user message with available details
    user_message_content = f"Create a lesson plan titled '{lesson_plan.title}'."
    if lesson_plan.objectives:
        user_message_content += f" The objectives are: '{lesson_plan.objectives}'."
    if lesson_plan.materials_needed:
        user_message_content += f" Materials needed: '{lesson_plan.materials_needed}'."
    if lesson_plan.plan_details:
        user_message_content += f" Plan details: '{lesson_plan.plan_details}'."

    # Call to GPT-4 API to generate LaTeX code for the lesson plan
    try:
        if ENVIRONMENT == "dev":
            with open(
                f"{settings.lesson_plans_dir}/lesson_plan_20231105124141.tex", "r"
            ) as file:
                latex_content = file.read()

        else:
            response = openai.ChatCompletion.create(
                model="gpt-4",  # Use the latest model or specify another if preferred
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant skilled in creating LaTeX lesson plans for tutors teaching young children in English in Hong Kong. Generate a complete lesson plan in LaTeX format based on the provided details. Create the lesson plan in a beautiful table format and add didactic hints to it. Also only output the LaTeX code an nothing else, before or after the code.",
                    },
                    {
                        "role": "user",
                        "content": user_message_content,
                    },
                ],
                temperature=0.7,  # Adjust as needed
                max_tokens=1024,  # Set limit for the completion
                n=1,  # Only one completion
                # stop=["\\end{document}"],  # LaTeX document end
            )

            # Extract the LaTeX content from the response
            latex_content = response.choices[0].message["content"]

        # Create a temporary file for the LaTeX content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tex") as temp_file:
            temp_file.write(latex_content.encode("utf-8"))
            temp_file_path = temp_file.name

        # Upload the .tex file to Supabase
        with open(temp_file_path, "rb") as file:
            tex_filename = (
                f"lesson_plan_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.tex"
            )
            upload_response = supabase.storage.from_("lesson_plans_tex").upload(
                tex_filename, file
            )
            print(f"upload_response: {upload_response}")

        # After uploading we can safely remove the temporary file
        os.remove(temp_file_path)

        return {"latex": latex_content}
    except openai.error.OpenAIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compile-latex/")
async def compile_latex_endpoint(tex_filename: str):
    # Step 1: Download the .tex file from Supabase
    tex_file_path = download_file_from_supabase(tex_filename)

    # Step 2: Compile the LaTeX file to PDF
    print(f"tex_file_path: {tex_file_path}")
    pdf_success, pdf_file_path = compile_latex_to_pdf(tex_file_path)

    if pdf_success:
        # Step 3: Upload the PDF file back to Supabase
        upload_pdf_to_supabase(pdf_file_path, tex_filename)

        # Clean up the local temporary .tex file
        os.remove(tex_file_path)

        # Clean up the local temporary .pdf file
        os.remove(pdf_file_path)

        return {
            "message": "Successfully compiled LaTeX to PDF.",
            "pdf_filename": pdf_file_path,  # Assuming you want to return the path
        }
    else:
        # Clean up the local temporary .tex file in case of failure as well
        os.remove(tex_file_path)
        raise HTTPException(status_code=500, detail="Error compiling LaTeX to PDF.")


# Helper function to download .tex file from Supabase
def download_file_from_supabase(tex_filename):
    # Assuming the file is stored in a bucket called 'lesson_plans_tex'
    download_response = supabase.storage.from_("lesson_plans_tex").download(
        tex_filename
    )
    print(download_response)

    # Write the file to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".tex") as temp_file:
        temp_file.write(download_response)
        return temp_file.name


def upload_pdf_to_supabase(pdf_file_path, tex_filename):
    pdf_filename = tex_filename.replace(".tex", ".pdf")

    # Check if the file already exists in Supabase storage
    existing_files = supabase.storage.from_("lesson_plans").list()
    existing_file_names = [file["name"] for file in existing_files]

    if pdf_filename in existing_file_names:
        # Delete the existing file first
        delete_response = supabase.storage.from_("lesson_plans").remove(pdf_filename)
        print(delete_response)

    # Now upload the new file
    with open(pdf_file_path, "rb") as pdf_file:
        upload_response = supabase.storage.from_("lesson_plans").upload(
            pdf_filename,
            pdf_file,
        )
        print(upload_response)

        print(f"File uploaded: {pdf_filename}")


def compile_latex_to_pdf(tex_file_path):
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
    result = subprocess.run(
        docker_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    pdf_file_path = tex_file_path.replace(".tex", ".pdf")

    return result.returncode == 0, pdf_file_path


# Health check endpoint
@app.get("/health/")
async def health_check():
    return {"status": "healthy"}
