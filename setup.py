"""
Phoenix Core - Production-Ready Python Framework
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="phoenix-core",
    version="1.0.0",
    author="Phoenix Team",
    author_email="team@phoenix.dev",
    description="Production-ready modular Python framework with AI routing, Telegram control, and GitHub integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/phoenix-team/phoenix-core",
    packages=find_packages(exclude=["tests", "tests.*", "docs", "scripts"]),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Communications :: Chat",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "pytest-cov>=4.0",
            "black>=23.0",
            "flake8>=6.0",
            "mypy>=1.0",
            "isort>=5.0",
        ],
        "docs": [
            "sphinx>=7.0",
            "sphinx-rtd-theme>=1.3",
        ],
    },
    entry_points={
        "console_scripts": [
            "phoenix=phoenix_core.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
