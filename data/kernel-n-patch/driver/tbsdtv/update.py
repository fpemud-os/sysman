#!/usr/bin/python3

import os
import robust_layer.simple_git

os.makedirs("./media_build", exist_ok=True)
robust_layer.simple_git.pull("./media_build", reclone_on_failure=True, url="https://github.com/tbsdtv/media_build")

os.makedirs("./linux_media", exist_ok=True)
robust_layer.simple_git.pull("./linux_media", reclone_on_failure=True, url="https://github.com/tbsdtv/linux_media")
