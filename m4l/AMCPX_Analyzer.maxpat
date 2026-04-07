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
		"rect" : [ 100, 100, 700, 440 ],
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
					"text" : "node.script amcpx_analyzer_server.js",
					"patching_rect" : [ 30.0, 230.0, 280.0, 22.0 ],
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
					"text" : "AMCPX Real-Time Analyzer — LUFS/RMS/crest factor on port 9880. Drop on any bus or master.",
					"patching_rect" : [ 30.0, 20.0, 520.0, 34.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-3",
					"maxclass" : "inlet~",
					"patching_rect" : [ 30.0, 70.0, 30.0, 30.0 ],
					"numinlets" : 0,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ],
					"comment" : "audio in L"
				}
			},
			{
				"box" : {
					"id" : "obj-4",
					"maxclass" : "inlet~",
					"patching_rect" : [ 80.0, 70.0, 30.0, 30.0 ],
					"numinlets" : 0,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ],
					"comment" : "audio in R"
				}
			},
			{
				"box" : {
					"id" : "obj-5",
					"maxclass" : "live.meter~",
					"patching_rect" : [ 30.0, 120.0, 150.0, 54.0 ],
					"numinlets" : 2,
					"numoutlets" : 5,
					"outlettype" : [ "signal", "signal", "", "", "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-6",
					"maxclass" : "newobj",
					"text" : "metro 100",
					"patching_rect" : [ 260.0, 120.0, 80.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "bang" ]
				}
			},
			{
				"box" : {
					"id" : "obj-7",
					"maxclass" : "newobj",
					"text" : "prepend meter_peak",
					"patching_rect" : [ 30.0, 185.0, 150.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-8",
					"maxclass" : "newobj",
					"text" : "prepend meter_rms",
					"patching_rect" : [ 200.0, 185.0, 150.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-9",
					"maxclass" : "newobj",
					"text" : "loadbang",
					"patching_rect" : [ 260.0, 75.0, 70.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 1,
					"outlettype" : [ "bang" ]
				}
			},
			{
				"box" : {
					"id" : "obj-10",
					"maxclass" : "newobj",
					"text" : "print amcpx_analyzer",
					"patching_rect" : [ 330.0, 230.0, 160.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 0
				}
			}
		],
		"lines" : [
			{
				"patchline" : {
					"source" : [ "obj-3", 0 ],
					"destination" : [ "obj-5", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-4", 0 ],
					"destination" : [ "obj-5", 1 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-9", 0 ],
					"destination" : [ "obj-6", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-6", 0 ],
					"destination" : [ "obj-5", 2 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 2 ],
					"destination" : [ "obj-7", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-5", 3 ],
					"destination" : [ "obj-8", 0 ]
				}
			},
			{
				"patchline" : {
					"source" : [ "obj-7", 0 ],
					"destination" : [ "obj-1", 0 ]
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
					"source" : [ "obj-1", 0 ],
					"destination" : [ "obj-10", 0 ]
				}
			}
		]
	}
}
