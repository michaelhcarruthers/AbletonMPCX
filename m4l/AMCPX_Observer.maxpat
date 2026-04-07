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
		"rect" : [ 100, 100, 780, 460 ],
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
					"text" : "node.script amcpx_observer_server.js",
					"patching_rect" : [ 30.0, 80.0, 280.0, 22.0 ],
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
					"text" : "AMCPX Observer — Selected Track / Device / Parameter / Playhead\nNode for Max TCP server on port 9879\nDrop on any MIDI track and leave running.",
					"patching_rect" : [ 30.0, 20.0, 500.0, 50.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-3",
					"maxclass" : "newobj",
					"text" : "print amcpx_observer",
					"patching_rect" : [ 30.0, 130.0, 160.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-4",
					"maxclass" : "newobj",
					"text" : "js lom_bridge.js",
					"patching_rect" : [ 340.0, 80.0, 160.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-5",
					"maxclass" : "newobj",
					"text" : "live.path live_set",
					"patching_rect" : [ 30.0, 190.0, 150.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-6",
					"maxclass" : "newobj",
					"text" : "live.observer current_song_time",
					"patching_rect" : [ 30.0, 230.0, 230.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-7",
					"maxclass" : "newobj",
					"text" : "speedlim 100",
					"patching_rect" : [ 30.0, 265.0, 100.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-8",
					"maxclass" : "newobj",
					"text" : "prepend current_song_time",
					"patching_rect" : [ 30.0, 300.0, 200.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-9",
					"maxclass" : "newobj",
					"text" : "live.path live_set view",
					"patching_rect" : [ 260.0, 190.0, 170.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-10",
					"maxclass" : "newobj",
					"text" : "live.observer selected_track",
					"patching_rect" : [ 260.0, 230.0, 210.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-11",
					"maxclass" : "newobj",
					"text" : "prepend selected_track",
					"patching_rect" : [ 260.0, 265.0, 175.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-12",
					"maxclass" : "newobj",
					"text" : "live.path live_set view selected_track view",
					"patching_rect" : [ 480.0, 190.0, 280.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-13",
					"maxclass" : "newobj",
					"text" : "live.observer selected_device",
					"patching_rect" : [ 480.0, 230.0, 215.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-14",
					"maxclass" : "newobj",
					"text" : "prepend selected_device",
					"patching_rect" : [ 480.0, 265.0, 180.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-15",
					"maxclass" : "newobj",
					"text" : "live.path live_set view selected_track view selected_device",
					"patching_rect" : [ 30.0, 350.0, 380.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-16",
					"maxclass" : "newobj",
					"text" : "live.observer selected_parameter",
					"patching_rect" : [ 30.0, 385.0, 230.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-17",
					"maxclass" : "newobj",
					"text" : "prepend selected_parameter",
					"patching_rect" : [ 30.0, 420.0, 190.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
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
					"destination" : [ "obj-4", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-4", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 0 ],
					"destination" : [ "obj-6", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-6", 0 ],
					"destination" : [ "obj-7", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-7", 0 ],
					"destination" : [ "obj-8", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-8", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-9", 0 ],
					"destination" : [ "obj-10", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-10", 0 ],
					"destination" : [ "obj-11", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-11", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-12", 0 ],
					"destination" : [ "obj-13", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-13", 0 ],
					"destination" : [ "obj-14", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-14", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-15", 0 ],
					"destination" : [ "obj-16", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-16", 0 ],
					"destination" : [ "obj-17", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-17", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			}
		]
	}
}
