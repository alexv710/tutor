# Tutor Lesson Plan Manager

Welcome to the Tutor Lesson Plan Manager repository. This application is designed specifically for tutors in Hong Kong to enhance their workflow in creating, improving, and managing lesson plans. The integration with AI through `langchain` and `chat-gpt-4` elevates the quality and effectiveness of the educational content provided.

## Features

- **Lesson Plan Creation**: Generate lesson plans using the advanced capabilities of GPT-4.
- **Content Improvement**: Refine existing educational materials with suggestions from AI.
- **Plan Management**: Store and manage lesson plans efficiently using a robust backend.
- **Live Editing**: Modify lesson plans in real-time with a LaTeX integrated editor.
- **PDF Viewing**: Easily view lesson plans in PDF format within the application.
- **User-friendly UI**: Utilize a sleek interface built with `streamlit` for a seamless user experience.

## Technology Stack

- **Backend**: FastAPI
- **Frontend**: Streamlit
- **AI**: OpenAI's GPT-4
- **Data Storage**: Supabase
- **Styling**: LaTeX for educational content formatting
- **Deployment**: Vercel for continuous deployment and hosting

## Local Development

To set up the project for local development, follow these steps:

1. **Clone the repository**

   ```sh
   git clone https://github.com/yourusername/tutor-lesson-plan-manager.git
   ```

2. **Install dependencies**

   Navigate to the project directory (backend and frontend separately), create a venv and install the required dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. **Environment Variables**

   Set up the necessary environment variables or `.env` file as per the project requirements.

4. **Run the Application**

   Execute the Streamlit application locally:

   ```sh
   streamlit run app.py
   ```

## Deployment - tbd

The application is configured for deployment on Vercel, ensuring easy updates and high availability. Follow the instructions provided by Vercel to deploy your instance of the application.

## Contributing - tbd

Contributions to the Tutor Lesson Plan Manager are welcome. Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests to us.

## License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.

---

For any queries or further assistance, please contact [Alex](alexander.wyss@protonmail.com).