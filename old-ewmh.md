## Issues in original [`ewmh` library](https://github.com/parkouss/pyewmh):
- Abandoned and unmaintained
	- Last release in 2016
	- Last commit in 2017
	- 9 open issues and 2 open pull requests. Most bugs not even reported anymore
- Incomplete, missing many features from the EWMH spec:
	- `_NET_SUPPORTED`
	- `_NET_DESKTOP_NAMES`
	- All features from 1.3 besides the new window types `_NET_WM_WINDOW_TYPE_*`
	- All features from 1.4 and latest 1.5
- Buggy
	- Never uses ChangeProperty, using ClientMessage for _all_ property writes.
	  As such, some property writes don't work:
		- `_NET_WM_NAME` / `set_wm_name()`: fail and raise exception
- Little customization and poorly chosen hardcoded values
	- `_NET_ACTIVE_WINDOW` / `set_active_window()`: lacks _source indication_ argument.
	  It uses a hardcoded 1, resulting in most WMs ignoring the request
- No Pythonic / OOP API
	- There's no Window object, all methods on same class and most require a window argument.
