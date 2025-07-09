from flask import Flask, render_template, request
import requests
import random
import google.generativeai as genai
import markdown2
from dotenv import load_dotenv
import os

app = Flask(__name__)

MIN_ATTEMPTS = 3

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        handle = request.form.get('handle', '').strip()
        if not handle:
            return render_template('index.html', error="Please enter a handle.")

        url = f"https://codeforces.com/api/user.status?handle={handle}"
        response = requests.get(url)
        data = response.json()

        if data.get('status') != 'OK':
            error_msg = data.get('comment', 'Unknown error from Codeforces API.')
            return render_template('index.html', error=f"API error: {error_msg}")

        submissions = data['result']
        attempted, solved = set(), set()
        problem_tags = {}
        problem_ratings = {}

        for sub in submissions:
            problem = sub.get('problem', {})
            contest_id = problem.get('contestId')
            index = problem.get('index')
            if contest_id is None or index is None:
                continue
            key = f"{contest_id}-{index}"
            tags = problem.get('tags', [])
            rating = problem.get('rating')
            problem_tags[key] = tags
            if rating:
                problem_ratings[key] = rating
            attempted.add(key)
            if sub.get('verdict') == 'OK':
                solved.add(key)

        tag_stats = {}

        for key in attempted:
            tags = problem_tags.get(key, [])
            rating = problem_ratings.get(key, None)
            for tag in tags:
                tag_stats.setdefault(tag, {'attempted': 0, 'solved': 0, 'ratings': []})
                tag_stats[tag]['attempted'] += 1
                if rating:
                    tag_stats[tag]['ratings'].append(rating)

        for key in solved:
            tags = problem_tags.get(key, [])
            for tag in tags:
                tag_stats.setdefault(tag, {'attempted': 0, 'solved': 0, 'ratings': []})
                tag_stats[tag]['solved'] += 1

        stats_list = []
        for tag, counts in tag_stats.items():
            attempted_count = counts['attempted']
            solved_count = counts['solved']
            success_rate = (solved_count / attempted_count) if attempted_count > 0 else 0
            avg_rating = round(sum(counts['ratings']) / len(counts['ratings']), 1) if counts['ratings'] else 'N/A'
            stats_list.append({
                'tag': tag,
                'attempted': attempted_count,
                'solved': solved_count,
                'rate': success_rate,
                'avg_rating': avg_rating
            })

        stats_list.sort(key=lambda x: x['tag'])
        weak_candidates = [s for s in stats_list if s['attempted'] >= MIN_ATTEMPTS]
        weak_tags = sorted(weak_candidates, key=lambda x: x['rate'])[:3]

        suggestions = []
        if weak_tags:
            prob_url = "https://codeforces.com/api/problemset.problems"
            prob_resp = requests.get(prob_url)
            prob_data = prob_resp.json()
            if prob_data.get('status') == 'OK':
                all_problems = prob_data['result']['problems']
                weak_tag_names = {wt['tag'] for wt in weak_tags}
                unsolved = []
                for prob in all_problems:
                    key = f"{prob.get('contestId')}-{prob.get('index')}"
                    if key in solved:
                        continue
                    prob_tags = set(prob.get('tags', []))
                    if prob_tags & weak_tag_names and 'rating' in prob:
                        unsolved.append(prob)
                unsolved.sort(key=lambda x: x['rating'])
                suggestions = unsolved[:5]

        summary_prompt = f"""
You're a professional competitive programming coach.

Given the user's Codeforces performance stats:
{stats_list}

Each entry contains:
- Tag
- Attempts
- Solves
- Success rate
- Average rating of problems tried in that tag

Analyze weak areas considering low success rate, high attempts, and difficulty of problems (based on average rating).
Then create a step-by-step training plan including:
- How many problems to solve
- What difficulty range to focus on
- Mixed tag integration
- Suggested number of contests
End with motivational advice.
Respond in structured markdown.
"""

        try:
            gemini_response = model.generate_content(summary_prompt)
            recommendation = markdown2.markdown(gemini_response.text.strip())
        except Exception as e:
            recommendation = f"<p>Could not generate training plan: {str(e)}</p>"

        return render_template(
            'results.html',
            handle=handle,
            tag_stats=stats_list,
            weak_tags=weak_tags,
            suggestions=suggestions,
            training_plan=recommendation
        )

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)