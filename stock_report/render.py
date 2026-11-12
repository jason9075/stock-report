"""只渲染本程式產生的簡單 Markdown，不依賴網路或第三方套件。"""
import html
import re


def inline(text):
    text = html.escape(text)
    return re.sub(r"\[([^\]]+)\]\((https://[^\s)]+)\)", r'<a href="\2">\1</a>', text)


def markdown_html(text):
    output, table, listing = [], False, False
    for line in text.splitlines() + [""]:
        if not line.startswith("|") and table:
            output.append("</table>"); table = False
        if not line.startswith("- ") and listing:
            output.append("</ul>"); listing = False
        if line.startswith("|"):
            if re.fullmatch(r"[| :\-]+", line):
                continue
            header = not table
            if header:
                output.append('<table cellpadding="8" cellspacing="0" border="0">'); table = True
            tag = "th" if header else "td"
            output.append("<tr>" + "".join(f"<{tag}>{inline(c.strip())}</{tag}>" for c in line.strip("|").split("|")) + "</tr>")
        elif line.startswith("# "):
            output.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("## "):
            output.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("- "):
            if not listing:
                output.append("<ul>"); listing = True
            output.append(f"<li>{inline(line[2:])}</li>")
        elif line:
            output.append(f"<p>{inline(line)}</p>")
    return "\n".join(output)
