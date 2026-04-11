{
	"patcher": {
		"fileversion": 1,
		"appversion": {
			"major": 9,
			"minor": 0,
			"revision": 10,
			"architecture": "x64",
			"modernui": 1
		},
		"rect": [
			100,
			100,
			860,
			800
		],
		"bglocked": 0,
		"openinpresentation": 0,
		"default_fontsize": 12.0,
		"default_fontface": 0,
		"default_fontname": "Arial",
		"gridonopen": 1,
		"gridsize": [
			15.0,
			15.0
		],
		"gridsnaponopen": 1,
		"objectsnaponopen": 1,
		"statusbarvisible": 2,
		"toolbarvisible": 1,
		"classnamespace": "box",
		"boxes": [
			{
				"box": {
					"id": "obj-1",
					"maxclass": "newobj",
					"text": "node.script amcpx_analyzer_server.js",
					"patching_rect": [
						30.0,
						230.0,
						280.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 2,
					"outlettype": [
						"",
						""
					],
					"saved_object_attributes": {
						"autostart": 1,
						"defer": 0,
						"watch": 1
					}
				}
			},
			{
				"box": {
					"id": "obj-3",
					"maxclass": "newobj",
					"text": "plugin~",
					"patching_rect": [
						30.0,
						55.0,
						44.0,
						20.0
					],
					"numinlets": 2,
					"numoutlets": 2,
					"outlettype": [
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-4",
					"maxclass": "newobj",
					"text": "plugout~",
					"patching_rect": [
						110.5,
						55.0,
						51.0,
						20.0
					],
					"numinlets": 2,
					"numoutlets": 2,
					"outlettype": [
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-6",
					"maxclass": "newobj",
					"text": "metro 100",
					"patching_rect": [
						365.0,
						120.0,
						80.0,
						20.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						"bang"
					]
				}
			},
			{
				"box": {
					"id": "obj-7",
					"maxclass": "newobj",
					"text": "prepend meter_peak",
					"patching_rect": [
						33.0,
						184.0,
						150.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-8",
					"maxclass": "newobj",
					"text": "prepend meter_rms",
					"patching_rect": [
						244.0,
						188.0,
						150.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-9",
					"maxclass": "newobj",
					"text": "loadbang",
					"patching_rect": [
						365.0,
						75.0,
						70.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"bang"
					]
				}
			},
			{
				"box": {
					"id": "obj-10",
					"maxclass": "newobj",
					"text": "print amcpx_analyzer",
					"patching_rect": [
						330.0,
						230.0,
						160.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-11",
					"maxclass": "newobj",
					"text": "route set_measuring",
					"patching_rect": [
						37.5,
						283.0,
						107.0,
						20.0
					],
					"numinlets": 2,
					"numoutlets": 2,
					"outlettype": [
						"",
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-12",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						37.0,
						140.0,
						36.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-13",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						244.0,
						140.0,
						36.0,
						20.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-14",
					"maxclass": "newobj",
					"text": "peakamp~ 100",
					"patching_rect": [
						33.0,
						103.5,
						77.0,
						20.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						"float"
					]
				}
			},
			{
				"box": {
					"id": "obj-21",
					"maxclass": "newobj",
					"text": "peakamp~ 4410",
					"patching_rect": [
						153.0,
						103.5,
						83.0,
						20.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						"float"
					]
				}
			},
			{
				"box": {
					"id": "obj-70",
					"maxclass": "newobj",
					"text": "\u2500\u2500 Tonal band analysis \u2500\u2500",
					"patching_rect": [
						30.0,
						330.0,
						300.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-71",
					"maxclass": "newobj",
					"text": "sub",
					"patching_rect": [
						30.0,
						350.0,
						60.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-72",
					"maxclass": "newobj",
					"text": "bass",
					"patching_rect": [
						140.0,
						350.0,
						60.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-73",
					"maxclass": "newobj",
					"text": "low_mid",
					"patching_rect": [
						250.0,
						350.0,
						70.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-74",
					"maxclass": "newobj",
					"text": "mid",
					"patching_rect": [
						360.0,
						350.0,
						60.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-75",
					"maxclass": "newobj",
					"text": "presence",
					"patching_rect": [
						470.0,
						350.0,
						80.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-76",
					"maxclass": "newobj",
					"text": "air",
					"patching_rect": [
						580.0,
						350.0,
						60.0,
						22.0
					],
					"numinlets": 0,
					"numoutlets": 0
				}
			},
			{
				"box": {
					"id": "obj-77",
					"maxclass": "newobj",
					"text": "svf~ 40 0.7",
					"patching_rect": [
						30.0,
						375.0,
						90.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 4,
					"outlettype": [
						"signal",
						"signal",
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-78",
					"maxclass": "newobj",
					"text": "svf~ 90 0.8",
					"patching_rect": [
						140.0,
						375.0,
						90.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 4,
					"outlettype": [
						"signal",
						"signal",
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-79",
					"maxclass": "newobj",
					"text": "svf~ 220 0.9",
					"patching_rect": [
						250.0,
						375.0,
						90.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 4,
					"outlettype": [
						"signal",
						"signal",
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-80",
					"maxclass": "newobj",
					"text": "svf~ 900 0.9",
					"patching_rect": [
						360.0,
						375.0,
						90.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 4,
					"outlettype": [
						"signal",
						"signal",
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-81",
					"maxclass": "newobj",
					"text": "svf~ 3500 0.9",
					"patching_rect": [
						470.0,
						375.0,
						100.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 4,
					"outlettype": [
						"signal",
						"signal",
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-82",
					"maxclass": "newobj",
					"text": "svf~ 9000 0.7",
					"patching_rect": [
						580.0,
						375.0,
						100.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 4,
					"outlettype": [
						"signal",
						"signal",
						"signal",
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-83",
					"maxclass": "newobj",
					"text": "abs~",
					"patching_rect": [
						30.0,
						415.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-84",
					"maxclass": "newobj",
					"text": "abs~",
					"patching_rect": [
						140.0,
						415.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-85",
					"maxclass": "newobj",
					"text": "abs~",
					"patching_rect": [
						250.0,
						415.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-86",
					"maxclass": "newobj",
					"text": "abs~",
					"patching_rect": [
						360.0,
						415.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-87",
					"maxclass": "newobj",
					"text": "abs~",
					"patching_rect": [
						470.0,
						415.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-88",
					"maxclass": "newobj",
					"text": "abs~",
					"patching_rect": [
						580.0,
						415.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-89",
					"maxclass": "newobj",
					"text": "slide~ 20 200",
					"patching_rect": [
						30.0,
						455.0,
						90.0,
						22.0
					],
					"numinlets": 3,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-90",
					"maxclass": "newobj",
					"text": "slide~ 20 200",
					"patching_rect": [
						140.0,
						455.0,
						90.0,
						22.0
					],
					"numinlets": 3,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-91",
					"maxclass": "newobj",
					"text": "slide~ 20 200",
					"patching_rect": [
						250.0,
						455.0,
						90.0,
						22.0
					],
					"numinlets": 3,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-92",
					"maxclass": "newobj",
					"text": "slide~ 20 200",
					"patching_rect": [
						360.0,
						455.0,
						90.0,
						22.0
					],
					"numinlets": 3,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-93",
					"maxclass": "newobj",
					"text": "slide~ 20 200",
					"patching_rect": [
						470.0,
						455.0,
						90.0,
						22.0
					],
					"numinlets": 3,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-94",
					"maxclass": "newobj",
					"text": "slide~ 20 200",
					"patching_rect": [
						580.0,
						455.0,
						90.0,
						22.0
					],
					"numinlets": 3,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			},
			{
				"box": {
					"id": "obj-95",
					"maxclass": "newobj",
					"text": "snapshot~ 50",
					"patching_rect": [
						30.0,
						495.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-96",
					"maxclass": "newobj",
					"text": "snapshot~ 50",
					"patching_rect": [
						140.0,
						495.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-97",
					"maxclass": "newobj",
					"text": "snapshot~ 50",
					"patching_rect": [
						250.0,
						495.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-98",
					"maxclass": "newobj",
					"text": "snapshot~ 50",
					"patching_rect": [
						360.0,
						495.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-99",
					"maxclass": "newobj",
					"text": "snapshot~ 50",
					"patching_rect": [
						470.0,
						495.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-100",
					"maxclass": "newobj",
					"text": "snapshot~ 50",
					"patching_rect": [
						580.0,
						495.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-101",
					"maxclass": "newobj",
					"text": "max 0.000001",
					"patching_rect": [
						30.0,
						535.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-102",
					"maxclass": "newobj",
					"text": "max 0.000001",
					"patching_rect": [
						140.0,
						535.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-103",
					"maxclass": "newobj",
					"text": "max 0.000001",
					"patching_rect": [
						250.0,
						535.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-104",
					"maxclass": "newobj",
					"text": "max 0.000001",
					"patching_rect": [
						360.0,
						535.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-105",
					"maxclass": "newobj",
					"text": "max 0.000001",
					"patching_rect": [
						470.0,
						535.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-106",
					"maxclass": "newobj",
					"text": "max 0.000001",
					"patching_rect": [
						580.0,
						535.0,
						90.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-107",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						30.0,
						575.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-108",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						140.0,
						575.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-109",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						250.0,
						575.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-110",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						360.0,
						575.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-111",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						470.0,
						575.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-112",
					"maxclass": "newobj",
					"text": "atodb",
					"patching_rect": [
						580.0,
						575.0,
						50.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-113",
					"maxclass": "flonum",
					"patching_rect": [
						30.0,
						615.0,
						60.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-114",
					"maxclass": "flonum",
					"patching_rect": [
						140.0,
						615.0,
						60.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-115",
					"maxclass": "flonum",
					"patching_rect": [
						250.0,
						615.0,
						60.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-116",
					"maxclass": "flonum",
					"patching_rect": [
						360.0,
						615.0,
						60.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-117",
					"maxclass": "flonum",
					"patching_rect": [
						470.0,
						615.0,
						60.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-118",
					"maxclass": "flonum",
					"patching_rect": [
						580.0,
						615.0,
						60.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-119",
					"maxclass": "newobj",
					"text": "prepend band_sub",
					"patching_rect": [
						30.0,
						655.0,
						120.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-120",
					"maxclass": "newobj",
					"text": "prepend band_bass",
					"patching_rect": [
						140.0,
						655.0,
						120.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-121",
					"maxclass": "newobj",
					"text": "prepend band_low_mid",
					"patching_rect": [
						250.0,
						655.0,
						130.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-122",
					"maxclass": "newobj",
					"text": "prepend band_mid",
					"patching_rect": [
						360.0,
						655.0,
						110.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-123",
					"maxclass": "newobj",
					"text": "prepend band_presence",
					"patching_rect": [
						470.0,
						655.0,
						140.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-124",
					"maxclass": "newobj",
					"text": "prepend band_air",
					"patching_rect": [
						580.0,
						655.0,
						110.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-125",
					"maxclass": "newobj",
					"text": "expr (($f1+$f2)/2.)-(($f3+$f4)/2.)",
					"patching_rect": [
						30.0,
						700.0,
						280.0,
						22.0
					],
					"numinlets": 4,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-126",
					"maxclass": "newobj",
					"text": "expr ((40*$f1)+(90*$f2)+(220*$f3)+(900*$f4)+(3500*$f5)+(9000*$f6)) / max(($f1+$f2+$f3+$f4+$f5+$f6), 0.001)",
					"patching_rect": [
						330.0,
						700.0,
						500.0,
						22.0
					],
					"numinlets": 6,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-127",
					"maxclass": "newobj",
					"text": "prepend spectral_tilt",
					"patching_rect": [
						30.0,
						740.0,
						140.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-128",
					"maxclass": "newobj",
					"text": "prepend spectral_centroid",
					"patching_rect": [
						330.0,
						740.0,
						160.0,
						22.0
					],
					"numinlets": 1,
					"numoutlets": 1,
					"outlettype": [
						""
					]
				}
			},
			{
				"box": {
					"id": "obj-130",
					"maxclass": "newobj",
					"text": "+~",
					"patching_rect": [
						30.0,
						78.0,
						44.0,
						22.0
					],
					"numinlets": 2,
					"numoutlets": 1,
					"outlettype": [
						"signal"
					]
				}
			}
		],
		"lines": [
			{
				"patchline": {
					"source": [
						"obj-1",
						0
					],
					"destination": [
						"obj-10",
						0
					],
					"order": 0
				}
			},
			{
				"patchline": {
					"source": [
						"obj-1",
						0
					],
					"destination": [
						"obj-11",
						0
					],
					"order": 1
				}
			},
			{
				"patchline": {
					"source": [
						"obj-11",
						0
					],
					"destination": [
						"obj-6",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-12",
						0
					],
					"destination": [
						"obj-7",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-13",
						0
					],
					"destination": [
						"obj-8",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-14",
						0
					],
					"destination": [
						"obj-12",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-21",
						0
					],
					"destination": [
						"obj-13",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						0
					],
					"destination": [
						"obj-14",
						0
					],
					"order": 2
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						0
					],
					"destination": [
						"obj-21",
						0
					],
					"order": 0
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						1
					],
					"destination": [
						"obj-4",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						0
					],
					"destination": [
						"obj-4",
						0
					],
					"order": 1
				}
			},
			{
				"patchline": {
					"source": [
						"obj-7",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-8",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-9",
						0
					],
					"destination": [
						"obj-6",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-77",
						0
					],
					"destination": [
						"obj-83",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-78",
						0
					],
					"destination": [
						"obj-84",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-79",
						0
					],
					"destination": [
						"obj-85",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-80",
						0
					],
					"destination": [
						"obj-86",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-81",
						0
					],
					"destination": [
						"obj-87",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-82",
						0
					],
					"destination": [
						"obj-88",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-83",
						0
					],
					"destination": [
						"obj-89",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-84",
						0
					],
					"destination": [
						"obj-90",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-85",
						0
					],
					"destination": [
						"obj-91",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-86",
						0
					],
					"destination": [
						"obj-92",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-87",
						0
					],
					"destination": [
						"obj-93",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-88",
						0
					],
					"destination": [
						"obj-94",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-89",
						0
					],
					"destination": [
						"obj-95",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-90",
						0
					],
					"destination": [
						"obj-96",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-91",
						0
					],
					"destination": [
						"obj-97",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-92",
						0
					],
					"destination": [
						"obj-98",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-93",
						0
					],
					"destination": [
						"obj-99",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-94",
						0
					],
					"destination": [
						"obj-100",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-95",
						0
					],
					"destination": [
						"obj-101",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-96",
						0
					],
					"destination": [
						"obj-102",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-97",
						0
					],
					"destination": [
						"obj-103",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-98",
						0
					],
					"destination": [
						"obj-104",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-99",
						0
					],
					"destination": [
						"obj-105",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-100",
						0
					],
					"destination": [
						"obj-106",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-101",
						0
					],
					"destination": [
						"obj-107",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-102",
						0
					],
					"destination": [
						"obj-108",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-103",
						0
					],
					"destination": [
						"obj-109",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-104",
						0
					],
					"destination": [
						"obj-110",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-105",
						0
					],
					"destination": [
						"obj-111",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-106",
						0
					],
					"destination": [
						"obj-112",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-107",
						0
					],
					"destination": [
						"obj-113",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-108",
						0
					],
					"destination": [
						"obj-114",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-109",
						0
					],
					"destination": [
						"obj-115",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-110",
						0
					],
					"destination": [
						"obj-116",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-111",
						0
					],
					"destination": [
						"obj-117",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-112",
						0
					],
					"destination": [
						"obj-118",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-113",
						0
					],
					"destination": [
						"obj-119",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-114",
						0
					],
					"destination": [
						"obj-120",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-115",
						0
					],
					"destination": [
						"obj-121",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-116",
						0
					],
					"destination": [
						"obj-122",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-117",
						0
					],
					"destination": [
						"obj-123",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-118",
						0
					],
					"destination": [
						"obj-124",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-119",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-120",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-121",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-122",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-123",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-124",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-113",
						0
					],
					"destination": [
						"obj-125",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-114",
						0
					],
					"destination": [
						"obj-125",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-116",
						0
					],
					"destination": [
						"obj-125",
						2
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-117",
						0
					],
					"destination": [
						"obj-125",
						3
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-113",
						0
					],
					"destination": [
						"obj-126",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-114",
						0
					],
					"destination": [
						"obj-126",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-115",
						0
					],
					"destination": [
						"obj-126",
						2
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-116",
						0
					],
					"destination": [
						"obj-126",
						3
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-117",
						0
					],
					"destination": [
						"obj-126",
						4
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-118",
						0
					],
					"destination": [
						"obj-126",
						5
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-125",
						0
					],
					"destination": [
						"obj-127",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-126",
						0
					],
					"destination": [
						"obj-128",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-127",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-128",
						0
					],
					"destination": [
						"obj-1",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						0
					],
					"destination": [
						"obj-130",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						1
					],
					"destination": [
						"obj-130",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-130",
						0
					],
					"destination": [
						"obj-77",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-130",
						0
					],
					"destination": [
						"obj-78",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-130",
						0
					],
					"destination": [
						"obj-79",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-130",
						0
					],
					"destination": [
						"obj-80",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-130",
						0
					],
					"destination": [
						"obj-81",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-130",
						0
					],
					"destination": [
						"obj-82",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-95",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-96",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-97",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-98",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-99",
						1
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-100",
						1
					]
				}
			}
		]
	}
}
