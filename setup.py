from setuptools import setup, find_packages

setup(
    name="pystou",
    version="0.1.0",
    description="Python scripts for deduplicating folders and unarchiving files",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/pystou",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "pystou=pystou.main:main",
        ],
    },
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
