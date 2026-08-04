# Install pylint
pip install pylint

# Run duplication check
pylint your_file.py --disable=all --enable=duplicate-code

# Check entire project
pylint **/*.py --disable=all --enable=duplicate-code