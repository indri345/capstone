import os
import re

files = [
    'cms/templates/cms/base.html'
]

navbar_css = """
        /* NAVBAR CSS */
        .navbar { background-color: #016632; position: sticky; top: 0; z-index: 1000; font-family: 'Poppins', sans-serif !important; padding-top: 12px; padding-bottom: 12px; }
        .navbar a { text-decoration: none !important; color: white; transition: 0.2s; font-family: 'Poppins', sans-serif !important; display: inline-block; }
        .navbar a:hover { transform: translateY(-2px); color: #ffc107 !important; }
        .active-link { font-weight: 600; border-bottom: 2px solid white; }
        .admin-btn { background: #ffc107; color: black !important; padding: 6px 20px; border-radius: 20px; font-weight: 600; margin-left: 5px; text-align: center; }
        .admin-btn:hover { background: #e0a800 !important; color: black !important; transform: translateY(-2px); }
        .brand-link { text-decoration: none !important; color: white; display: inline-flex; align-items: center; gap: 10px; font-weight: 500; font-family: 'Poppins', sans-serif !important; }
        .brand-logo { width: 28px; height: 28px; }
        @media (max-width: 767.98px) {
            .navbar-collapse {
                background-color: #016632;
                padding: 15px 10px;
                border-top: 1px solid rgba(255,255,255,0.1);
                margin-top: 10px;
            }
            .nav-links-container {
                flex-direction: column;
                align-items: flex-start !important;
                gap: 15px !important;
                width: 100%;
            }
            .admin-btn {
                margin-left: 0 !important;
                width: 100%;
                text-align: center;
            }
            .active-link {
                border-bottom: none;
                border-left: 3px solid white;
                padding-left: 8px;
            }
        }
"""

navbar_html = """<nav class="navbar navbar-expand-md navbar-dark">
    <div class="container-fluid px-4">
        <a class="navbar-brand brand-link" href="/">
            <img class="brand-logo" src="{% static 'cms/pegadaian_logo.png' %}" alt="Logo">
            <span>Digital Culture</span>
        </a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
            <div class="d-flex align-items-center ms-auto gap-3 nav-links-container">
                <a href="/" class="{% if request.path == '/' %}active-link{% endif %}">Home</a>
                <a href="/explore/" class="{% if request.path == '/explore/' %}active-link{% endif %}">Explore</a>
                <a href="/culture_performance/" class="{% if request.path == '/culture_performance/' %}active-link{% endif %}">Culture</a>
                <a href="/business_performance/" class="{% if request.path == '/business_performance/' %}active-link{% endif %}">Business</a>
                <a href="/admin-home/" class="admin-btn">Login</a>
            </div>
        </div>
    </div>
</nav>"""

for f in files:
    with open(f, 'r') as file:
        content = file.read()
    
    # Needs {% load static %} if not present
    if '{% load static %}' not in content:
        content = '{% load static %}\n' + content

    content = re.sub(r'<nav class="navbar.*?</nav>', navbar_html, content, flags=re.DOTALL)
    
    content = re.sub(r'\.navbar\s*\{[^}]*\}', '', content)
    content = re.sub(r'\.navbar a\s*\{[^}]*\}', '', content)
    
    if '</style>' in content:
        content = content.replace('</style>', f'{navbar_css}\n    </style>')
    
    with open(f, 'w') as file:
        file.write(content)

print("Updated base.html successfully!")
