## Setup & Installation

1. Clone the repository
```bash
git clone <repo-url>
cd <repo-name>
```

2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

OR
```bash
conda create -n myenv python=3.9.6
conda activate myenv
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

5. Create .env file
```bash
HF_TOKEN=your_huggingface_token_here
```
Get token: https://huggingface.co/settings/tokens

6. Input folder
Place PDF file inside:
```bash
input/
```

7. Run
```bash
python main.py
```
