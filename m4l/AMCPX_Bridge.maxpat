{
	"patcher" : {
		"fileversion" : 1,
		"appversion" : {
			"major" : 8,
			"minor" : 6,
			"revision" : 0,
			"architecture" : "x64",
			"modernui" : 1
		},
		"rect" : [ 100, 100, 700, 400 ],
		"bglocked" : 0,
		"openinpresentation" : 0,
		"default_fontsize" : 12.0,
		"default_fontface" : 0,
		"default_fontname" : "Arial",
		"gridonopen" : 1,
		"gridsize" : [ 15.0, 15.0 ],
		"gridsnaponopen" : 1,
		"objectsnaponopen" : 1,
		"statusbarvisible" : 2,
		"toolbarvisible" : 1,
		"boxes" : [
			{
				"box" : {
					"id" : "obj-1",
					"maxclass" : "newobj",
					"text" : "node.script amcpx_node_server.js",
					"patching_rect" : [ 30.0, 80.0, 260.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"saved_object_attributes" : {
						"autostart" : 1,
						"defer" : 0,
						"watch" : 1
					}
				}
			},
			{
				"box" : {
					"id" : "obj-2",
					"maxclass" : "comment",
					"text" : "AMCPX Bridge v2 — Arrangement View Access\nNode for Max TCP server on port 9878\njs lom_bridge.js routes LOM queries via route object\nDrop on any track and leave running.",
					"patching_rect" : [ 30.0, 20.0, 500.0, 50.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-3",
					"maxclass" : "newobj",
					"text" : "print amcpx",
					"patching_rect" : [ 30.0, 280.0, 100.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-4",
					"maxclass" : "newobj",
					"text" : "js lom_bridge.js",
					"patching_rect" : [ 310.0, 200.0, 160.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-5",
					"maxclass" : "newobj",
					"text" : "route live_get live_getcount live_call live_get_notes_extended",
					"patching_rect" : [ 310.0, 130.0, 400.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 5,
					"outlettype" : [ "", "", "", "", "" ]
				}
			}
		],
		"lines" : [
			{
				"patchline" : {
					"source" : [ "obj-1", 0 ],
					"destination" : [ "obj-3", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-1", 0 ],
					"destination" : [ "obj-5", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 0 ],
					"destination" : [ "obj-4", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 1 ],
					"destination" : [ "obj-4", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 2 ],
					"destination" : [ "obj-4", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 3 ],
					"destination" : [ "obj-4", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-4", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			}
		]
	}
}
