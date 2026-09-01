# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'tikworks'
copyright = '2025, Arda Kutlu'
author = 'Arda Kutlu'
release = '1.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    # Google-style Args:/Returns:/Raises: sections are the house docstring
    # style (AI/documentation_rules.md). Without napoleon they render as
    # block quotes and definition lists, which is where most of the build's
    # docutils warnings came from.
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx_toolbox.collapse',
    'sphinxcontrib.youtube',
    'autoapi.extension',
]

# One tree, rooted at the package itself. Listing sub-packages as well would
# document them twice, under both their real dotted path and a truncated one,
# which is what made cross-references ambiguous.
autoapi_dirs = ['../../src/python/tik']
autoapi_type = 'python'
autoapi_ignore = [
    '*setup*',
    '*shiboken*',
    '*PySide2*',
    '*PySide6*',
    '*PyQt5*',
    '*PyQt6*',
    '*external/**/*',
]
autoapi_file_patterns = ['*.py']
add_module_names = False
autoapi_member_order = 'groupwise'
autoapi_python_use_implicit_namespaces = True
# autoapi_own_page_level = "attribute"
autodoc_typehints = "signature"

autoapi_options = [ 'members', 'undoc-members', 'show-inheritance', 'show-module-summary', 'imported-members', ]


templates_path = ['_templates']

html_logo = '_static/logo.png'

exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
