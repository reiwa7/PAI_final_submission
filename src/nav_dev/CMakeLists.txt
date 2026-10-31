cmake_minimum_required(VERSION 3.8)
project(nav_dev)
set(CMAKE_CXX_STANDARD 17)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(key_event_msgs REQUIRED)
find_package(key_event_nodes REQUIRED)
add_executable(teleop_node src/teleop_node.cpp)
ament_target_dependencies(teleop_node
  rclcpp rclcpp_components geometry_msgs
  key_event_msgs key_event_nodes)
install(TARGETS teleop_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch config models
  DESTINATION share/${PROJECT_NAME})
ament_package()
