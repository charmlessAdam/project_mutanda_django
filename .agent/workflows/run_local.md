---
description: Run the Django backend locally
---

1. Create a virtual environment
```bash
python -m venv venv
```

2. Install dependencies
```bash
.\venv\Scripts\pip install -r requirements.txt
```

3. Run database migrations
```bash
.\venv\Scripts\python manage.py migrate
```

4. Start the development server
```bash
.\venv\Scripts\python manage.py runserver
```
