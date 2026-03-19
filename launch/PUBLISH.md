# Vigil Launch Checklist

## 1. PyPI Publish
```bash
# Create account at pypi.org if you don't have one
# Generate API token at pypi.org/manage/account/token/

# Save token
cat > ~/.pypirc << 'EOF'
[pypi]
username = __token__
password = pypi-YOUR-TOKEN-HERE
EOF

# Build + upload
cd /root/vigil
python3 -m build
python3 -m twine upload dist/*
```

## 2. Hacker News
- Go to news.ycombinator.com/submit
- Title: `Show HN: Vigil – Awareness daemon and frame-based tool filtering for AI agents`
- URL: `https://github.com/AlexlaGuardia/Vigil`
- Text: Copy from /root/vigil/launch/SHOW_HN.md (the "Text" section)
- Best time: Weekday morning, US Eastern (Tue-Thu, 8-10am)

## 3. Dev.to
- Go to dev.to/new
- Copy /root/vigil/launch/DEVTO_POST.md
- Set published: true when ready
- Add cover image (optional but helps)

## 4. Reddit (optional)
- r/MachineLearning (Self-post Sunday)
- r/LocalLLaMA
- r/ClaudeAI (if MCP-focused angle)

## 5. Post-Launch
- Reply to every HN comment within 2 hours
- Find something to agree with in objections before responding
- Share the HN link on Twitter/X
- Link Dev.to article back to GitHub

## Launch Order
1. PyPI (so `pip install` works)
2. HN (primary distribution)
3. Dev.to (same day, few hours later)
4. Reddit (next day if HN gets traction)
