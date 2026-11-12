"""Nord palette shared by the desktop UI and exported reports."""
POLAR_NIGHT = ('#2e3440', '#3b4252', '#434c5e', '#4c566a')
SNOW_STORM = ('#d8dee9', '#e5e9f0', '#eceff4')
FROST = ('#8fbcbb', '#88c0d0', '#81a1c1', '#5e81ac')
RED, GREEN, YELLOW = '#bf616a', '#a3be8c', '#ebcb8b'
MUTED = '#b0bbcc'

REPORT_CSS = '''
body{font:15px/1.8 system-ui;background:#2e3440;color:#d8dee9;max-width:1280px;margin:40px auto;padding:0 28px}
h1,h2{color:#eceff4;letter-spacing:.02em}h1{font-size:28px}h2{margin-top:36px;font-size:19px}
table{border-collapse:collapse;display:block;overflow:auto;background:#3b4252;border-radius:8px}
td,th{padding:12px 18px;border-bottom:1px solid #434c5e;white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
th{color:#88c0d0;font-weight:500}th:first-child,td:first-child{text-align:left}
a{color:#88c0d0}li{margin:8px 0}p{color:#d8dee9}
'''
