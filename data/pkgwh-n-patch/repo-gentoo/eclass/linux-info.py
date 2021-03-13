#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import subprocess

subprocess.run(["/usr/bin/patch", "-s", "-d", ".", "-p", "1"], input="""
diff --git a/linux-info.eclass b/linux-info.eclass
index 16740a3..f9941a4 100644
--- a/linux-info.eclass
+++ b/linux-info.eclass
@@ -731,7 +731,7 @@ check_extra_config() {
 			return 0
 		fi
 	else
-		require_configured_kernel
+		linux_config_exists
 	fi
 
 	einfo "Checking for suitable kernel configuration options..."
""", universal_newlines=True)
