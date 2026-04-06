{
	"patcher" : 	{
		"fileversion" : 1,
		"appversion" : 		{
			"major" : 8,
			"minor" : 6,
			"revision" : 0,
			"architecture" : "x64",
			"modernui" : 1
		},
		"classnamespace" : "dsp.gen",
		"rect" : [ 100, 100, 640, 480 ],
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
		"lefttoolbarpinned" : 0,
		"toptoolbarpinned" : 0,
		"righttoolbarpinned" : 0,
		"bottomtoolbarpinned" : 0,
		"toolbars_unpinned_last_save" : 0,
		"eventsource" : -1,
		"indexofkeyreviewer" : -1,
		"checkboxreadonly" : 0,
		"enabledsegreduit" : 0,
		"boxes" : [ 			{
				"box" : 				{
					"id" : "obj-1",
					"maxclass" : "newobj",
					"text" : "node.script amcpx_node_server.js",
					"patching_rect" : [ 30.0, 80.0, 260.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : 				{
					"id" : "obj-2",
					"maxclass" : "comment",
					"text" : "AMCPX Bridge v2\nArrangement View Access via Node for Max\nDrop on any MIDI track and leave running.",
					"patching_rect" : [ 30.0, 20.0, 400.0, 50.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : 				{
					"id" : "obj-3",
					"maxclass" : "newobj",
					"text" : "print amcpx",
					"patching_rect" : [ 30.0, 130.0, 100.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 0
				}
			},
			{
				"box" : 				{
					"id" : "obj-4",
					"maxclass" : "newobj",
					"text" : "loadbang",
					"patching_rect" : [ 30.0, 180.0, 70.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "bang" ]
				}
			},
			{
				"box" : 				{
					"id" : "obj-5",
					"maxclass" : "message",
					"text" : "start",
					"patching_rect" : [ 30.0, 210.0, 50.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			}
		],
		"lines" : [ 			{
				"patchline" : 				{
					"source" : [ "obj-1", 0 ],
					"destination" : [ "obj-3", 0 ]
				}
			},
			{
				"patchline" : 				{
					"source" : [ "obj-4", 0 ],
					"destination" : [ "obj-5", 0 ]
				}
			},
			{
				"patchline" : 				{
					"source" : [ "obj-5", 0 ],
					"destination" : [ "obj-1", 0 ]
				}
			}
		]
	}
}
