{
  "patcher": {
    "fileversion": 1,
    "appversion": {"major": 8, "minor": 6, "revision": 0},
    "rect": [100, 100, 600, 400],
    "boxes": [
      {
        "box": {
          "id": "obj-1",
          "maxclass": "newobj",
          "text": "js amcpx_bridge.js",
          "patching_rect": [50, 150, 200, 22]
        }
      },
      {
        "box": {
          "id": "obj-2",
          "maxclass": "newobj",
          "text": "mxj net.tcp.server 9878",
          "patching_rect": [50, 50, 200, 22]
        }
      },
      {
        "box": {
          "id": "obj-3",
          "maxclass": "comment",
          "text": "AMCPX Bridge - Arrangement View Access\nDrop on any track and leave running.",
          "patching_rect": [280, 50, 280, 40]
        }
      },
      {
        "box": {
          "id": "obj-4",
          "maxclass": "toggle",
          "patching_rect": [50, 20, 20, 20]
        }
      },
      {
        "box": {
          "id": "obj-5",
          "maxclass": "comment",
          "text": "Running",
          "patching_rect": [80, 22, 60, 20]
        }
      }
    ],
    "lines": [
      {"patchline": {"source": ["obj-2", 0], "destination": ["obj-1", 0]}},
      {"patchline": {"source": ["obj-1", 0], "destination": ["obj-2", 0]}}
    ]
  }
}
