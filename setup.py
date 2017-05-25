from setuptools import setup, find_packages
setup(
    name="linkapp.gateway",
    version="0.1",
    packages=["linkapp.gateway"],
    install_requires=['redis', 'pika', 'strict_rfc3339', 'jsonschema', 'webob', 'requests', 'pystache'],
    include_package_data=True
)