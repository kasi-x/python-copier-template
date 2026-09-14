"""The ros2 project_type: ament_python / ament_cmake layouts, the apt and pixi
distros, and how the ament build coexists with the standard CPython toolchain."""

from pathlib import Path

from support import copy_project_recommended


def test_template_log_library_skipped_for_ros2(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # ros2 packages use rclpy's own node logger; logging_setup.py isn't generated
    assert not list(tmp_path.rglob("logging_setup.py"))


def test_template_ros2_python_apt(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # ament_python layout
    assert (tmp_path / "package.xml").exists()
    assert "ament_python" in (tmp_path / "package.xml").read_text()
    assert "<depend>rclpy</depend>" in (tmp_path / "package.xml").read_text()
    assert (tmp_path / "setup.py").exists()
    assert (tmp_path / "setup.cfg").exists()
    assert (tmp_path / "resource" / "recommended_example").exists()
    assert (tmp_path / "test" / "test_flake8.py").exists()
    assert (tmp_path / "recommended_example" / "main.py").exists()
    # The standard toolchain coexists: pyproject has [project] (no rclpy dep —
    # package.xml owns the ROS deps), uv.lock and Dockerfile are generated.
    pyproject = (tmp_path / "pyproject.toml").read_text()
    assert "[project]" in pyproject
    assert "requires-python" in pyproject
    assert "rclpy" not in pyproject
    assert (tmp_path / "uv.lock").exists()
    assert (tmp_path / "Dockerfile").exists()
    # Humble -> Python 3.10
    assert (tmp_path / ".python-version").read_text().strip() == "3.10"
    # CI uses industrial_ci (apt flavour)
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "industrial_ci" in ci
    assert "ROS_DISTRO: humble" in ci
    # ros2-specific Dockerfile + the standard one coexist
    dockerfile = (tmp_path / "Dockerfile.ros2").read_text()
    assert "ros:humble-ros-base" in dockerfile
    # justfile drives colcon
    justfile = (tmp_path / "justfile").read_text()
    assert "colcon build" in justfile


def test_template_ros2_cpp_apt(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="cpp",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # ament_cmake layout
    assert (tmp_path / "CMakeLists.txt").exists()
    assert "ament_cmake" in (tmp_path / "package.xml").read_text()
    assert "<depend>rclcpp</depend>" in (tmp_path / "package.xml").read_text()
    assert (tmp_path / "src" / "talker.cpp").exists()
    assert (tmp_path / "include" / "recommended_example" / "talker.hpp").exists()
    # C++ package: the build is CMake, so no pyproject.toml/setup.py is needed
    # (the standard toolchain files stay, but the ament build is authoritative).
    assert not (tmp_path / "pyproject.toml").exists()
    assert not (tmp_path / "setup.py").exists()


def test_template_ros2_python_pixi(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="jazzy",
        ros2_package_manager="pixi",
    )
    # pixi.toml with the RoboStack distro channel
    pixi = (tmp_path / "pixi.toml").read_text()
    assert "robostack-jazzy" in pixi
    assert "ros-jazzy-rclpy" in pixi
    # Jazzy -> Python 3.12
    assert (tmp_path / ".python-version").read_text().strip() == "3.12"
    # CI uses setup-pixi
    ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
    assert "setup-pixi" in ci
    assert "industrial_ci" not in ci
    # Dockerfile.ros2 pixi flavour
    dockerfile = (tmp_path / "Dockerfile.ros2").read_text()
    assert "pixi install" in dockerfile
    # pixi manages everything: no justfile, package_manager is pixi
    assert not (tmp_path / "justfile").exists()
    assert (tmp_path / "pixi.lock").exists()
    # pyproject still coexists (dev tooling config)
    assert (tmp_path / "pyproject.toml").exists()
    assert "[project]" in (tmp_path / "pyproject.toml").read_text()


def test_template_ros2_coexists_with_standard_tooling(tmp_path: Path):
    copy_project_recommended(
        tmp_path,
        project_type="ros2",
        pkg_language="python",
        ros_distro="humble",
        ros2_package_manager="apt",
    )
    # Docs and dev tooling all coexist with the ament layout; the ASCII
    # banner was removed template-wide, so no banner tooling is generated.
    assert (tmp_path / "docs").exists()
    assert not (tmp_path / "tools" / "ascii_banner.py").exists()
    assert not (tmp_path / "NOTICE").exists()
    # The ros2 package __init__ exports __version__ (docs import it)
    init = (tmp_path / "recommended_example" / "__init__.py").read_text()
    assert "__version__" in init
    # devcontainer is ROS-aware and rendered (no raw jinja)
    devcontainer = (tmp_path / ".devcontainer" / "devcontainer.json").read_text()
    assert "Dockerfile.ros2" in devcontainer
    assert "{%" not in devcontainer
