"""Small missing symbolic assets in the installed theme's legacy stylesheet."""
def fallbacks():
    svg=lambda body:f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><g fill="#bebebe">{body}</g></svg>'.encode()
    assets={
        'check-symbolic.svg':svg('<path d="m2 8 4 4 8-8-1.5-1.5L6 9 3.5 6.5Z"/>'),
        'dash-symbolic.svg':svg('<rect x="3" y="7" width="10" height="2" rx="1"/>'),
        'bullet-symbolic.svg':svg('<circle cx="8" cy="8" r="4"/>'),
        'text-select-start-symbolic.svg':svg('<path d="M8 0h2v8a5 5 0 1 1-2 0Z"/>'),
        'text-select-end-symbolic.svg':svg('<path d="M6 0h2v8a5 5 0 1 1-2 0Z"/>'),
    }
    for name,path in [('horz-scale-has-marks-above','M8 1 15 8v6H1V8Z'),('horz-scale-has-marks-below','M1 2h14v6l-7 7-7-7Z'),('vert-scale-has-marks-above','M1 8 8 1h6v14H8Z'),('vert-scale-has-marks-below','M2 1h6l7 7-7 7H2Z')]:
        assets['slider-'+name+'-symbolic.svg']=svg(f'<path d="{path}"/>')
    return {'gtk-3.0/assets/'+name:data for name,data in assets.items()}
