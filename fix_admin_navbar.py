import os
import re

files = [
    'cms/templates/cms/admin.html',
    'cms/templates/cms/explore_admin.html',
    'cms/templates/cms/feedback_admin.html'
]

navbar_css = """
        /* NAVBAR ADMIN CSS */
        .navbar { background: linear-gradient(to right, #3b82f6, #60a5fa); display: flex; justify-content: space-between; padding: 15px 40px; align-items: center; position: sticky; top: 0; z-index: 1000; }
        .logo { color: white; font-weight: 600; text-decoration: none; font-size: 18px; }
        .nav-links { display: flex; align-items: center; }
        .nav-links a { color: rgba(255, 255, 255, 0.9); text-decoration: none; margin-left: 20px; font-size: 14px; font-weight: 500; transition: 0.3s; }
        .nav-links a:hover, .nav-links a.active { color: white; font-weight: 600; }
        @media (max-width: 600px) {
            .navbar {
                flex-direction: column;
                gap: 12px;
                padding: 15px 20px;
                align-items: center;
            }
            .nav-links {
                width: 100%;
                justify-content: center;
                flex-wrap: wrap;
                gap: 10px;
            }
            .nav-links a {
                margin-left: 0;
                font-size: 13px;
                padding: 4px 8px;
            }
        }
"""

navbar_html = """    <div class="navbar">
        <a href="{% url 'home' %}" class="logo">Digital Culture</a>
        <div class="nav-links">
            <a href="/admin-home/" class="{% if request.path == '/admin-home/' %}active{% endif %}">Control</a>
            <a href="/admin-explore/" class="{% if request.path == '/admin-explore/' %}active{% endif %}">Explore</a>
            <a href="/admin-feedback/" class="{% if request.path == '/admin-feedback/' %}active{% endif %}">Feedback</a>
            <a href="{% url 'admin_logout' %}" style="background:#ef4444;color:white;padding:5px 14px;border-radius:20px;margin-left:15px;font-size:13px;font-weight:600;">Logout</a>
        </div>
    </div>"""

for f in files:
    if not os.path.exists(f):
        print(f"File {f} not found!")
        continue
        
    with open(f, 'r') as file:
        content = file.read()
    
    # Replace navbar HTML block
    # We find <div class="navbar"> ... </div> (ensure we match the right one)
    content = re.sub(r'<div class="navbar">.*?</div>\s*</div>', navbar_html, content, flags=re.DOTALL)
    
    # Wait, the regex `.*?</div>\s*</div>` matches until the second closing div.
    # Let's use a more precise regex.
    content = re.sub(r'<div class="navbar">.*?(?=^\s*<div class="container")|<div class="navbar">.*?(?=^\s*<div class="dashboard-wrapper")', navbar_html + '\n\n', content, flags=re.DOTALL | re.MULTILINE)
    
    # Clean up old CSS
    content = re.sub(r'\.navbar\s*\{[^}]*\}', '', content)
    content = re.sub(r'\.logo\s*\{[^}]*\}', '', content)
    content = re.sub(r'\.nav-links\s*a\s*\{[^}]*\}', '', content)
    content = re.sub(r'\.nav-links\s*a:hover,\s*\.nav-links\s*a\.active\s*\{[^}]*\}', '', content)
    content = re.sub(r'/\*\s*NAVBAR ADMIN CSS\s*\*/', '', content)
    content = re.sub(r'/\*\s*NAVBAR\s*\*/', '', content)
    
    # Inject new CSS right before </style>
    if '</style>' in content:
        content = content.replace('</style>', f'{navbar_css}\n    </style>')
    
    with open(f, 'w') as file:
        file.write(content)

print("Admin navbars updated successfully!")
