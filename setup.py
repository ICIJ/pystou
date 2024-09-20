from setuptools import setup, find_packages

setup(
    name="pystou",
    version="0.0.0",
    description="Python scripts for deduplicating folders and unarchiving files",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/pystou",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "dedup_folders=dedup_folders.main:main",
            "unarchive=unarchive.main:main",
        ],
    },
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
