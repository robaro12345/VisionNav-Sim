from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'synapse_bringup'

# collect files in launch/ to install to share/<package>/launch/
launch_files = []
for f in glob(os.path.join(os.path.dirname(__file__), 'launch', '*')):
    if os.path.isfile(f):
        launch_files.append(os.path.relpath(f, start=os.path.dirname(__file__)))

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),('share/synapse_bringup/rviz', glob('rviz/*')),
    ('share/synapse_bringup/worlds', glob('worlds/*')),('share/synapse_bringup/urdf', glob('urdf/*')),
    ('share/synapse_bringup/config', glob('config/*'))
]
if launch_files:
    data_files.append((f'share/{package_name}/launch', [os.path.join('launch', os.path.basename(p)) for p in launch_files]))

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=data_files,
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='omkar',
    maintainer_email='omkar@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'context_node = synapse_bringup.context_node:main',
        ],
    },
)
