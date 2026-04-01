# Orchenize Legacy

> **AI-assisted academic organizer and scheduling web application**

Orchenize (Legacy) is a Flask-based web application designed to help students organize their academic life. It combines traditional course/assignment management with AI-powered scheduling assistance using Google's Gemini AI.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.x-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Orchenize is available right now!
[Go use it!](acoder152.pythonanywhere.com)
> **Disclaimer:** The code on the repo may not fully match the code in production.

### Quick notes
Orchenize started development in Feb 2025, was launched June 2025, and is now being open sourced.
This repo will occasionally be updated with any code changes.

 ## Features

- **Weekly Calendar View** - Visual schedule with support for daily/weekly recurring events
- **Course Management** - Add, edit, and track your courses
- **Assignment Tracking** - Manage assignments with due dates, progress tracking, and priority weights
- **AI-Powered Scheduling** - Generate optimized study schedules using Google Gemini AI
- **User Authentication** - Secure multi-user support with individual databases
- **Custom Periods** - Create color-coded time blocks for your daily routine
- **Progress Tracking** - Visual progress indicators for assignments

## Usage

1. **Register** a new account at `/register`
2. **Add Courses** - Define your academic courses
3. **Add Assignments** - Track homework, projects, and deadlines
4. **Set Periods** - Block out your regular schedule (classes, meals, sleep)
5. **Use AI Arrange** - Let AI optimize your study schedule
6. **View Calendar** - See your weekly schedule at a glance

## AI Features

### AI Schedule Arrangement
The AI can intelligently arrange your study schedule based on:
- Your existing calendar commitments
- Assignment due dates and priorities
- Custom regimen intensity (Very Low → Very High)
- Expected time requirements per assignment

### AI Settings
Configure your AI preferences:
- Model selection (default: `gemini-2.5-flash`)
- Study regimen intensity
- Custom scheduling preferences

## Quickstart for self downloading

### Prerequisites

- Python 3.8 or higher
- Google Gemini API key (for AI features)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/A-coder152/orchenize
   cd orchenize
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env`:
   ```env
   FLASK_SECRET_KEY=your-secret-key-here
   GOOGLE_GENAI_API_KEY=your-gemini-api-key
   GOOGLE_GENAI_MODEL=gemini-2.5-flash
   DATABASE_PATH=database.db
   FLASK_SECURE_COOKIES=false  # Set to true for production
   ```

5. **Run the application**
   ```bash
   python app.py
   ```
   
   Or for production:
   ```bash
   gunicorn app:app
   ```

6. **Access the app**
   
   Open your browser and navigate to `http://localhost:5000`

## Project Structure

```
Orchenize Legacy/
├── app.py                 # Main Flask application (~1100 lines)
├── database.db            # SQLite database
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── *.html                # HTML templates
│   ├── account.html
│   ├── add_assignment.html
│   ├── add_course.html
│   ├── ai_arrange.html
│   ├── ai_settings.html
│   ├── assignments.html
│   ├── edit_period.html
│   ├── john.html         # Main calendar view
│   ├── login.html
│   ├── register.html
│   └── view_*.html
└── README.md
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python, Flask |
| **Database** | SQLite |
| **AI** | Google Gemini API |
| **Frontend** | HTML5, CSS3, JavaScript |
| **Icons** | Font Awesome |
| **Deployment** | Gunicorn |

## Database Schema

The application uses SQLite with the following tables:

- **users** - User accounts (name, username, password, AI preferences)
- **courses** - Course information with color coding
- **assignments** - Assignments with due dates, progress, priority weights
- **periods** - Scheduled time blocks (recurring support: daily/weekly)

## Security

- Password hashing with Werkzeug
- Session-based authentication
- CSRF protection ready
- Secure cookie support (configurable)
- SQL injection prevention via parameterized queries

## Configuration

| Environment Variable | Description | Required |
|---------------------|-------------|----------|
| `FLASK_SECRET_KEY` | Flask session secret | Yes |
| `GOOGLE_GENAI_API_KEY` | Google Gemini API key | For AI features |
| `GOOGLE_GENAI_MODEL` | AI model to use | No (default: gemini-2.5-flash) |
| `DATABASE_PATH` | SQLite database path | No (default: database.db) |
| `FLASK_SECURE_COOKIES` | Enable HTTPS-only cookies | No (default: true) |

## Legacy Notice

> This is a **legacy version** of the Orchenize project. It represents an earlier implementation and may lack modern features, optimizations, or best practices found in newer versions.

Potential improvements for future versions:
- [ ] PostgreSQL/MySQL support
- [ ] REST API endpoints
- [ ] Mobile-responsive design improvements
- [ ] Real-time collaboration features
- [ ] Export to Google Calendar/iCal
- [ ] Email notifications for deadlines

## License

This project is open-source. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Flask](https://flask.palletsprojects.com/)
- AI powered by [Google Gemini](https://ai.google.dev/)
- Icons by [Font Awesome](https://fontawesome.com/)

---

**Made with ❤️ for students who need help organizing their academic life**
