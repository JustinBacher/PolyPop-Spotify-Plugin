require "imagegroup"

local repeat_states = { track="Song", context="Enabled", off="Disabled" }
local current_vol = nil

Instance.devices = { }
Instance.UserImageGroup = nil

Instance.properties = properties({
	{ name="Settings", type="PropertyGroup", items={
		{ name="Login", type="Action" },
		{ name="Status", type="Text", value="Disconnected", ui={readonly=true} },
		{ name="Device", type="PropertyGroup", items={
			{ name="PlaybackDevice", type="Enum", items=Instance.devices, onUpdate="onDeviceUpdate" },
			{ name="RefreshDevices", type="Action" }
		}, ui={expand=false} }
	} },
	{ name="Controls", type="PropertyGroup", ui={expand=false}, items={
		{ name="Play", type="Action" },
		{ name="Pause", type="Action" },
		{ name="Next", type="Action" },
		{ name="Previous", type="Action" },
		{ name="Modes", type="PropertyGroup", ui={expand=false}, items={
			{ name="Shuffle", type="Bool", value=false, onUpdate="onShuffleUpdate" },
			{ name="Repeat", type="Enum", items={
				"Disabled", "Enabled", "Song"
			}, value="Disabled", onUpdate="onRepeatUpdate" }
		} },
		{ name="Playlist", type="Enum", items={"No Playlists"} },
		{ name="PlayPlaylist", type="Action" },
		{ name="Volume", type="Real", units="NormalPercent", range={
			min=0, max=1
		}, ui={stride=0.2}, value=1, onUpdate="onVolumeUpdate" },
		{ name="Search", type="PropertyGroup", ui={expand=false}, items={
			{ name="QueryString", type="Text" },
			{ name="Queue", type="Action" }
		} }
	} },
	{ name="Alerts", type="PropertyGroup", items={
		{ name="onSongChange", type="Alert", args={
			title="[Title]",
			artist="[Artist]",
			requested_by="[Requested_By]",
			cover_image_url="[URL]"} },
		{ name="onPlay", type="Alert", args={
			title="[Title]",
			artist="[Artist]",
			requested_by="[Requested_By]",
			cover_image_url="[URL]"} },
		{ name="onPause", type="Alert" }
	} }
} )

function Instance:onInit( )
    --getOS( ):run("Spotify Service", getLocalFolder( ) .. "ppspotify.exe")
	self.properties.Settings.Status = "Disconnected"
	self.UserImageGroup = createImageGroup(self:getObjectKit( ), "UserImageGroup")
	self:connect( )
end

function Instance:send(cmd)
	if not self.webSocket or not self.webSocket:isConnected( ) then
		return
	end

	self.webSocket:send(cmd)
end

function Instance:send_action(action, data)
	if data then
		return self:send(json.encode({ action, data }))
	end

	self:send(json.encode({ action }))
end

function Instance:connect( )
	local host = getNetwork( ):getHost("localhost")
	self.webSocket = host:openWebSocket("ws://localhost:38045/ws")
	self.webSocket:setAutoReconnect(true)

	-- Event Listeners
	self.webSocket:addEventListener("onMessage", self, self.onMessage)
	self.webSocket:addEventListener("onConnected", self, self._onWsConnected)
	self.webSocket:addEventListener("onDisconnected", self, self._onWsDisconnected)
end

function Instance:_onWsConnected( )
	-- todo:
end

function Instance:_onWsDisconnected( )
	-- TODO:
end

function Instance:onSpotifyConnect(data)
	getUI( ):setUIProperty({
		{ obj=self.properties:find("Controls"), expand=true },
		{ obj=self.properties:find("Alerts"), expand=true }
	} )

	self.properties.Settings.Status = "Connected as: " .. data.name
	self.devices.all_devices = data.devices
	self.properties.Settings.Device:find("PlaybackDevice"):setElements(self.devices.all_devices)

	local tblImages = { }
	tblImages["Profile Image"] =data.user_image_url
	self.UserImageGroup:setObjects(tblImages)

	local playlists = { }
	self.playlists = data.playlists

	for k, _ in pairs(data.playlists) do
		table.insert(playlists, k)
		print(k .. ": " .. _)
	end

	self.properties.Controls:find("Playlist"):setElements(playlists)

	if not self.devices.current_device then
		self.devices.current_device = data.current_device
	end

	self.properties.Controls.Modes.Shuffle = data.shuffle_state
	self.properties.Controls.Modes:find("Repeat").value = repeat_states[data.repeat_state]

	if not self.devices.current_device then
		return
	end

	local device_list = {}
	
	for k, _ in pairs(data.devices) do
		table.insert(device_list,  k)
	end

	self.properties.Settings.Device:find("PlaybackDevice"):setElements(device_list)

	for _, v in pairs(self.devices.all_devices) do
		if self.devices.current_device == v then
			return end
		self.properties.Settings.Device:find("PlaybackDevice"):setValue(v)
	end

end

function Instance:onMessage(msg)
	local payload = json.decode(msg)
	local action, data = payload.action, payload.data

	print('"' .. tostring(action) .. '", ' .. tostring(data))

	local case = {
		["spotify_connect"] = function( )
			self:onSpotifyConnect(data)
		end,

		["song_changed"] = function( )
			self:onSongChanged(data)
		end,

		["update"] = function( )
			self:onUpdateSettings(data)
		end,

		["devices"] = function( )
			self.devices.all_devices =data.devices
			self.properties.Settings.Device:find("PlaybackDevice"):setElements(
				self.devices.all_devices
			)
		end,

		["error"] = function( )
			if data.command == "play" then
				self.devices.current_device = nil
				self:PlayPlaylist( )
			end
		end
	}

	if case[action] then
		case[action]( )
	else
		log( msg )
	end

end

function Instance:Login( )
	self:send_action("login")
end


function Instance:Play(playlist_uri)
	local device_name = self.properties.Settings.Device:find("PlaybackDevice"):getValue( )
	local playlist_arg = ""

	if playlist_uri then
		playlist_arg = { playlist_uri=playlist_uri }
	end

	self:send_action("play", { device_name=device_name .. playlist_arg })
end


function Instance:Pause( )
	self:send_action("pause")
end

function Instance:Next( )
	self:send_action("next")
end

function Instance:Previous( )
	self:send_action("previous")
end

function Instance:onShuffleUpdate( )
	self:send_action("update", {
		shuffle_state=self.properties.Controls.Modes:find("Shuffle"):getValue( )
	} )
end

function Instance:onRepeatUpdate( )
	self:send_action("update", {
		repeat_state=self.properties.Controls.Modes:find("Repeat"):getValue( )
	} )
end

function Instance:onVolumeUpdate( )
	local new_volume = math.floor(
		self.properties.Controls:find("Volume"):getValue( ) * 100 / 15
	) * 15

	if current_vol ~= new_volume then
		print(new_volume)
		self:send_action("update", {volume=new_volume})
		current_vol = new_volume
	end

end

function Instance:onSongChanged(data)
	local tblImages = { }
	tblImages["Profile Image"] = data.item.album.images[2].url
	self.UserImageGroup:setObjects(tblImages)
	self.properties.Alerts.onSongChange:raise( )
end

function Instance:RefreshDevices( )
	self:send_action("get_devices")
end

function Instance:onUpdateSettings(data)
	if data.shuffle_state ~= nil then
		self.properties.Controls.Modes.Shuffle = data.shuffle_state
	end
	if data.repeat_state then
		self.properties.Controls.Modes:find("Repeat"):setValue(repeat_states[data.repeat_state])
	end
	if data.volume then
		self.properties.Controls.Volume = data.volume
	end
end

function Instance:PlayPlaylist( )
	self:Play(self.playlists[self.properties.Controls:find("Playlist"):getValue( )])
end

function Instance:disconnect( )
	if (self.webSocket and self.webSocket:isConnected( )) then
		self:send_action("disconnect")
		if (self.webSocket) then
			self.webSocket:disconnect( )
		end
	end
end
