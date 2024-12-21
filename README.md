# Deezer Graph Search: Connect artists, albums and tracks

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://pydantic.dev)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)


<p align="center">
  <a href="https://deezer-graph-api-38e2480498ba.herokuapp.com/docs" target="_blank">
    <img src="https://github.com/tandpfun/skill-icons/blob/main/icons/FastAPI.svg" style="width:50px;height:50px;">
  </a>
</p>

---

## Endpoints

| Name                          | Description                                                                  | Endpoint | Returns         | Task Enabled | Status                       |
|-------------------------------|------------------------------------------------------------------------------|----------|-----------------|--------------|------------------------------|
| Search anything with keywords | Get a list of result with only keywords and list of types allowed            | /search  | Nodes and Edges | Yes          | Available :white_check_mark: |
| Expand around existing node   | Fill i.e. get artist from album and Explore i.e. Get similar albums          | /expand  | Nodes and Edges | Yes          | Available :white_check_mark: |
| Delete a node                 | If cascading, successors are deleted too. Graph is oriented from query node. | /delete  | Deleted Nodes   | No           | Available :white_check_mark: |
| Search hipster mode           | Search but encourage less popular results                                    | TDB      | Nodes and Edges | TBD          | Coming :technologist:        |

Some endpoints are task enabled to allow for incremental result as they may take longer. They return a _task_id_ to check task status and result.

---

## Policies
Feedbacks and contributions are greatly appreciated.

For questions, please feel free to reach out [by email](mailto:thomas.dambrin@gmail.com?subject=[GitHub]%20Deezer%20Graph%20API).
