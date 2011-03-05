from setuptools import setup, find_packages
setup(
    name = "cafepress",
    version = "0.1",
    py_modules = ['cafepress'],
    scripts = [],

    install_requires = ['httplib2==0.6.0', 'elementtree==1.2.7-20070827-preview', 'urllib3==0.3.1'],

    package_data = {
    },

    # metadata for upload to PyPI
    author = "Arpad Ray",
    author_email = "arraypad@gmail.com",
    description = "Client for Cafepress API",
    license = "LGPL",
    keywords = "cafepress print api",
    url = "http://hexy.org/",   # project home page, if any

    # could also include long_description, download_url, classifiers, etc.
)

