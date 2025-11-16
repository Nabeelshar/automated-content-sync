#!/bin/bash

echo "F95Zone Crawler - GitHub Repository Setup"
echo "=========================================="
echo ""

# Check if we're in the correct directory
if [ ! -f "crawler.py" ]; then
    echo "Error: crawler.py not found. Please run this script from the github-repo directory."
    exit 1
fi

# Initialize git if not already initialized
if [ ! -d ".git" ]; then
    echo "Initializing Git repository..."
    git init
    echo "✓ Git initialized"
else
    echo "✓ Git already initialized"
fi

# Add all files
echo ""
echo "Adding files to Git..."
git add .
echo "✓ Files added"

# Commit
echo ""
echo "Creating initial commit..."
git commit -m "Initial commit: F95Zone WordPress Crawler

Features:
- Automated crawling of F95Zone game threads
- WordPress REST API integration
- Image proxy for hotlink protection
- Duplicate detection
- Batch processing
- GitHub Actions workflow (runs every 6 hours)"
echo "✓ Initial commit created"

# Prompt for repository URL
echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo ""
echo "1. Create a new repository on GitHub"
echo "2. Copy the repository URL (e.g., https://github.com/username/f95zone-crawler.git)"
echo ""
read -p "Enter your GitHub repository URL: " REPO_URL

if [ -n "$REPO_URL" ]; then
    echo ""
    echo "Adding remote origin..."
    git remote add origin "$REPO_URL"
    echo "✓ Remote added"
    
    echo ""
    echo "Pushing to GitHub..."
    git branch -M main
    git push -u origin main
    echo "✓ Pushed to GitHub"
    
    echo ""
    echo "=========================================="
    echo "Setup Complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Go to your repository on GitHub"
    echo "2. Go to Settings → Secrets and variables → Actions"
    echo "3. Add the following secrets:"
    echo "   - WORDPRESS_API_URL"
    echo "   - WORDPRESS_API_KEY"
    echo "   - F95_CSRF_TOKEN"
    echo "   - F95_SESSION_TOKEN"
    echo "   - F95_USER_TOKEN"
    echo ""
    echo "4. Go to Actions tab and enable workflows"
    echo "5. The crawler will run automatically every 6 hours"
    echo "   or you can trigger it manually from the Actions tab"
    echo ""
else
    echo ""
    echo "No repository URL provided. To push later, run:"
    echo "  git remote add origin <your-repo-url>"
    echo "  git branch -M main"
    echo "  git push -u origin main"
    echo ""
fi
