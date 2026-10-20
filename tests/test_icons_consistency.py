import re
from pathlib import Path

def test_fa_icons_consistency():
    """
    Varre index.html, app.js e ui.js e falha se alguma classe fa-* usada não estiver definida em icons.css.
    Garante que nenhum ícone seja exibido como quadrado no navegador.
    """
    root_dir = Path(__file__).resolve().parent.parent
    files = [
        root_dir / 'frontend' / 'index.html',
        root_dir / 'frontend' / 'js' / 'app.js',
        root_dir / 'frontend' / 'js' / 'ui.js'
    ]

    used_icons = set()
    for file_path in files:
        assert file_path.exists(), f"Arquivo não encontrado: {file_path}"
        content = file_path.read_text(encoding='utf-8')
        for match in re.findall(r'fa-[a-z0-9-]+', content):
            used_icons.add(match)

    css_path = root_dir / 'frontend' / 'css' / 'icons.css'
    assert css_path.exists(), f"icons.css não encontrado: {css_path}"
    css_content = css_path.read_text(encoding='utf-8')

    defined_icons = set(re.findall(r'\.(fa-[a-z0-9-]+)', css_content))

    # Classes utilitárias do FontAwesome que não são ícones de conteúdo
    util_classes = {'fa-solid', 'fa-regular', 'fa-brands', 'fa-spin', 'fa-2x', 'fa-3x', 'fa-xs', 'fa-sm', 'fa-lg'}

    missing_icons = sorted(list((used_icons - defined_icons) - util_classes))

    assert len(missing_icons) == 0, (
        f"Foram encontradas classes de ícones fa-* no frontend sem definição SVG em icons.css: {missing_icons}. "
        "Adicione as máscaras SVG correspondentes em frontend/css/icons.css."
    )
