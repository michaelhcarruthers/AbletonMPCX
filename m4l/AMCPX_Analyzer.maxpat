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
			},
			{
				"box" : {
					"id" : "obj-11",
					"maxclass" : "newobj",
					"text" : "svf~ 40 0.7",
					"patching_rect" : [ 30.0, 290.0, 90.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 4,
					"outlettype" : [ "signal", "signal", "signal", "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-12",
					"maxclass" : "newobj",
					"text" : "svf~ 90 0.8",
					"patching_rect" : [ 140.0, 290.0, 90.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 4,
					"outlettype" : [ "signal", "signal", "signal", "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-13",
					"maxclass" : "newobj",
					"text" : "svf~ 220 0.9",
					"patching_rect" : [ 250.0, 290.0, 90.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 4,
					"outlettype" : [ "signal", "signal", "signal", "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-14",
					"maxclass" : "newobj",
					"text" : "svf~ 900 0.9",
					"patching_rect" : [ 360.0, 290.0, 90.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 4,
					"outlettype" : [ "signal", "signal", "signal", "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-15",
					"maxclass" : "newobj",
					"text" : "svf~ 3500 0.9",
					"patching_rect" : [ 470.0, 290.0, 100.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 4,
					"outlettype" : [ "signal", "signal", "signal", "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-16",
					"maxclass" : "newobj",
					"text" : "svf~ 9000 0.7",
					"patching_rect" : [ 580.0, 290.0, 100.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 4,
					"outlettype" : [ "signal", "signal", "signal", "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-17",
					"maxclass" : "newobj",
					"text" : "abs~",
					"patching_rect" : [ 30.0, 330.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-18",
					"maxclass" : "newobj",
					"text" : "abs~",
					"patching_rect" : [ 140.0, 330.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-19",
					"maxclass" : "newobj",
					"text" : "abs~",
					"patching_rect" : [ 250.0, 330.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-20",
					"maxclass" : "newobj",
					"text" : "abs~",
					"patching_rect" : [ 360.0, 330.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-21",
					"maxclass" : "newobj",
					"text" : "abs~",
					"patching_rect" : [ 470.0, 330.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-22",
					"maxclass" : "newobj",
					"text" : "abs~",
					"patching_rect" : [ 580.0, 330.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-23",
					"maxclass" : "newobj",
					"text" : "slide~ 20 200",
					"patching_rect" : [ 30.0, 370.0, 90.0, 22.0 ],
					"numinlets" : 3,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-24",
					"maxclass" : "newobj",
					"text" : "slide~ 20 200",
					"patching_rect" : [ 140.0, 370.0, 90.0, 22.0 ],
					"numinlets" : 3,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-25",
					"maxclass" : "newobj",
					"text" : "slide~ 20 200",
					"patching_rect" : [ 250.0, 370.0, 90.0, 22.0 ],
					"numinlets" : 3,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-26",
					"maxclass" : "newobj",
					"text" : "slide~ 20 200",
					"patching_rect" : [ 360.0, 370.0, 90.0, 22.0 ],
					"numinlets" : 3,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-27",
					"maxclass" : "newobj",
					"text" : "slide~ 20 200",
					"patching_rect" : [ 470.0, 370.0, 90.0, 22.0 ],
					"numinlets" : 3,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-28",
					"maxclass" : "newobj",
					"text" : "slide~ 20 200",
					"patching_rect" : [ 580.0, 370.0, 90.0, 22.0 ],
					"numinlets" : 3,
					"numoutlets" : 1,
					"outlettype" : [ "signal" ]
				}
			},
			{
				"box" : {
					"id" : "obj-29",
					"maxclass" : "newobj",
					"text" : "snapshot~ 50",
					"patching_rect" : [ 30.0, 410.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-30",
					"maxclass" : "newobj",
					"text" : "snapshot~ 50",
					"patching_rect" : [ 140.0, 410.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-31",
					"maxclass" : "newobj",
					"text" : "snapshot~ 50",
					"patching_rect" : [ 250.0, 410.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-32",
					"maxclass" : "newobj",
					"text" : "snapshot~ 50",
					"patching_rect" : [ 360.0, 410.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-33",
					"maxclass" : "newobj",
					"text" : "snapshot~ 50",
					"patching_rect" : [ 470.0, 410.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-34",
					"maxclass" : "newobj",
					"text" : "snapshot~ 50",
					"patching_rect" : [ 580.0, 410.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-35",
					"maxclass" : "newobj",
					"text" : "max 0.000001",
					"patching_rect" : [ 30.0, 450.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-36",
					"maxclass" : "newobj",
					"text" : "max 0.000001",
					"patching_rect" : [ 140.0, 450.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-37",
					"maxclass" : "newobj",
					"text" : "max 0.000001",
					"patching_rect" : [ 250.0, 450.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-38",
					"maxclass" : "newobj",
					"text" : "max 0.000001",
					"patching_rect" : [ 360.0, 450.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-39",
					"maxclass" : "newobj",
					"text" : "max 0.000001",
					"patching_rect" : [ 470.0, 450.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-40",
					"maxclass" : "newobj",
					"text" : "max 0.000001",
					"patching_rect" : [ 580.0, 450.0, 90.0, 22.0 ],
					"numinlets" : 2,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-41",
					"maxclass" : "newobj",
					"text" : "atodb",
					"patching_rect" : [ 30.0, 490.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-42",
					"maxclass" : "newobj",
					"text" : "atodb",
					"patching_rect" : [ 140.0, 490.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-43",
					"maxclass" : "newobj",
					"text" : "atodb",
					"patching_rect" : [ 250.0, 490.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-44",
					"maxclass" : "newobj",
					"text" : "atodb",
					"patching_rect" : [ 360.0, 490.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-45",
					"maxclass" : "newobj",
					"text" : "atodb",
					"patching_rect" : [ 470.0, 490.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-46",
					"maxclass" : "newobj",
					"text" : "atodb",
					"patching_rect" : [ 580.0, 490.0, 50.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-47",
					"maxclass" : "flonum",
					"patching_rect" : [ 30.0, 530.0, 60.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-48",
					"maxclass" : "flonum",
					"patching_rect" : [ 140.0, 530.0, 60.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-49",
					"maxclass" : "flonum",
					"patching_rect" : [ 250.0, 530.0, 60.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-50",
					"maxclass" : "flonum",
					"patching_rect" : [ 360.0, 530.0, 60.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-51",
					"maxclass" : "flonum",
					"patching_rect" : [ 470.0, 530.0, 60.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-52",
					"maxclass" : "flonum",
					"patching_rect" : [ 580.0, 530.0, 60.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-53",
					"maxclass" : "newobj",
					"text" : "prepend band_sub",
					"patching_rect" : [ 30.0, 570.0, 120.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-54",
					"maxclass" : "newobj",
					"text" : "prepend band_bass",
					"patching_rect" : [ 140.0, 570.0, 120.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-55",
					"maxclass" : "newobj",
					"text" : "prepend band_low_mid",
					"patching_rect" : [ 250.0, 570.0, 130.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-56",
					"maxclass" : "newobj",
					"text" : "prepend band_mid",
					"patching_rect" : [ 390.0, 570.0, 110.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-57",
					"maxclass" : "newobj",
					"text" : "prepend band_presence",
					"patching_rect" : [ 470.0, 570.0, 140.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-58",
					"maxclass" : "newobj",
					"text" : "prepend band_air",
					"patching_rect" : [ 580.0, 570.0, 110.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-59",
					"maxclass" : "comment",
					"text" : "sub",
					"patching_rect" : [ 30.0, 270.0, 60.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-60",
					"maxclass" : "comment",
					"text" : "bass",
					"patching_rect" : [ 140.0, 270.0, 60.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-61",
					"maxclass" : "comment",
					"text" : "low_mid",
					"patching_rect" : [ 250.0, 270.0, 70.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-62",
					"maxclass" : "comment",
					"text" : "mid",
					"patching_rect" : [ 360.0, 270.0, 60.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-63",
					"maxclass" : "comment",
					"text" : "presence",
					"patching_rect" : [ 470.0, 270.0, 80.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-64",
					"maxclass" : "comment",
					"text" : "air",
					"patching_rect" : [ 580.0, 270.0, 60.0, 22.0 ],
					"numinlets" : 0,
					"numoutlets" : 0
				}
			},
			{
				"box" : {
					"id" : "obj-65",
					"maxclass" : "newobj",
					"text" : "expr (($f1+$f2)/2.)-(($f3+$f4)/2.)",
					"patching_rect" : [ 30.0, 620.0, 280.0, 22.0 ],
					"numinlets" : 4,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-66",
					"maxclass" : "newobj",
					"text" : "expr ((40*$f1)+(90*$f2)+(220*$f3)+(900*$f4)+(3500*$f5)+(9000*$f6)) / max(($f1+$f2+$f3+$f4+$f5+$f6), 0.001)",
					"patching_rect" : [ 330.0, 620.0, 500.0, 22.0 ],
					"numinlets" : 6,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-67",
					"maxclass" : "newobj",
					"text" : "prepend spectral_tilt",
					"patching_rect" : [ 30.0, 660.0, 140.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-68",
					"maxclass" : "newobj",
					"text" : "prepend spectral_centroid",
					"patching_rect" : [ 330.0, 660.0, 160.0, 22.0 ],
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ]
				}
			},
			{
				"box" : {
					"id" : "obj-69",
					"maxclass" : "comment",
					"text" : "── Tonal band analysis (wire manually) ──",
					"patching_rect" : [ 30.0, 255.0, 380.0, 22.0 ],
					"numinlets" : 0,
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
