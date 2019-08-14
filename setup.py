import setuptools

setuptools.setup(
    name="ahbench",
    version="0.0.1",
    author="L. Kärkkäinen",
    author_email="tronic@users.noreply.github.com",
    description="",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/Tronic/named1",
    packages=setuptools.find_packages(),
    classifiers = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires = ["wrk"],
    extras_require = {
        "trio": ["trio>=0.12"],
        "uvloop": ["uvloop"],
    },
    include_package_data = True,
)
