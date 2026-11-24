from importlib.metadata import version, PackageNotFoundError
for name in ('torch','torchvision','flwr','numpy','PyYAML','pytest','setuptools','wheel','build','matplotlib','pandas','pluggy','anyio'):
    try: print(f'{name}={version(name)}')
    except PackageNotFoundError: print(f'{name}=NOT_INSTALLED')
