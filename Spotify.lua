require "imagegroup"

local repeat_states = { track='Song', context='Enabled', off='Disabled' }

Instance.devices = {}

Instance.properties = properties({
	{ name="client_id", type="Text" },
	{ name="client_secret", type="Text" },
	{ name="Settings", type="PropertyGroup", items={
		{ name="Login", type="Action" },
		{ name="Status", type="Text", value="Disconnected", ui={readonly=true} },
		{ name="Device", type="PropertyGroup", items={
			{ name="PlaybackDevice", type="Enum", items=Instance.devices, onUpdate="onDeviceUpdate" },
			{ name="RefreshDevices", type="Action" }
		}, ui={expand=false}}
	}},
	{ name="Controls", type="PropertyGroup", ui={expand=false}, items={
		{ name="Play", type="Action" },
		{ name="Pause", type="Action" },
		{ name="Next", type="Action" },
		{ name="Previous", type="Action" },
		{ name="Modes", type="PropertyGroup", ui={expand=false}, items={
			{ name="Shuffle", type="Bool", value=False, onUpdate="onShuffleUpdate" },
			{ name="Repeat", type="Enum", items={"Disabled", "Enabled", "Song"}, value='Disabled', onUpdate="onRepeatUpdate" }
		}},
		{ name="Playlist", type="Enum", items={"No Playlists"}},
		{ name="PlayPlaylist", type="Action" },
		{ name="Volume", type="Real", units="NormalPercent", range={min=0, max=1}, ui={stride=0.2}, value=1, onUpdate="onVolumeUpdate" },
		{ name="Search", type="PropertyGroup", ui={expand=false}, items={
			{ name="QueryString", type="Text" },
			{ name="Queue", type="Action" }
		}}
	}},
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
			cover_image_url="[URL]"}},
		{ name="onPause", type="Alert" }
	}}
})

Instance.UserImageGroup = nil

function Instance:onInit()
    getOS():run("Spotify Service", getLocalFolder() .. "ppspotify.exe")
	getUI():setUIProperty({
		{ obj=self.properties:find("client_id"), visible=false },
		{ obj=self.properties:find("client_secret"), visible=false },
	})
	self.properties.Settings.Status = "Disconnected"
	self.UserImageGroup = createImageGroup(self:getObjectKit(), "UserImageGroup")
	self:connect()
end

function Instance:send(cmd)
	if (not self.webSocket or not self.webSocket:isConnected()) then
		return
	end

	self.webSocket:send(cmd)
end

function Instance:connect()
	self:attemptConnection()
end

function Instance:attemptConnection()
	local host = getNetwork():getHost("localhost")
	self.webSocket = host:openWebSocket("ws://localhost:38041")
	self.webSocket:setAutoReconnect(true)

	self.webSocket:addEventListener("onMessage", self, self.onMessage)
	self.webSocket:addEventListener("onConnected", self, self._onWsConnected)
	self.webSocket:addEventListener("onDisconnected", self, self._onWsDisconnected)

end

function Instance:_onWsConnected()
	self.webSocket:send(json.encode(
		{ action="connected_handshake",data={ client_id=self.properties.client_id, client_secret=self.properties.client_secret } }
	))
end

function Instance:_onWsDisconnected()

end

function Instance:onSpotifyConnect(data)
	getUI():setUIProperty({
		{ obj=self.properties:find("Controls"), expand=true },
		{ obj=self.properties:find("Alerts"), expand=true }
	})

	self.properties.Settings.Status = "Connected as: " ..data.name
	self.properties.client_id =data.client_id
	self.properties.client_secret =data.client_secret
	self.devices.all_devices =data.devices
	self.properties.Settings.Device:find("PlaybackDevice"):setElements(self.devices.all_devices)

	local tblImages = {}
	tblImages["Profile Image"] =data.user_image_url
	self.UserImageGroup:setObjects(tblImages)
	
	local playlists = {}
	self.playlists = data.playlists
	for k, _ in pairs(data.playlists) do
		table.insert(playlists, k)
	end
	self.properties.Controls:find("Playlist"):setElements(playlists)
	
	if not self.devices.current_device then
		self.devices.current_device =data.current_device
	end

	self.properties.Controls.Modes.Shuffle = data.shuffle_state
	self.properties.Controls.Modes:find("Repeat").value = repeat_states[data.repeat_state]
	self.properties.Controls.Volume = data.volume

	local device_in_devices = false
	if not self.devices.current_device then
		return
	end
	print(self.devices.current_device)
	for _, v in pairs(self.devices.all_devices) do
		if self.devices.current_device == v then
			return end
		device_in_devices = True
		self.properties.Settings.Device:find("PlaybackDevice"):setValue(v)
	end

end

function Instance:onMessage(msg)
	local payload = json.decode(msg)
	local action, data = payload.action, payload.data

	if action == 'spotify_connect' then
		self:onSpotifyConnect(data)
	end
	if action == 'song_changed' then
		self:onSongChanged(data)
	end
	if action == 'update' then
		self:onUpdateSettings(data)
	end
	if action == 'devices' then
		self.devices.all_devices =data.devices
		self.properties.Settings.Device:find("PlaybackDevice"):setElements(self.devices.all_devices)
	end

	if action == 'error' then
		local command = data.command
		if data.command == 'play' then
			self.devices.current_device = nil
			self:PlayPlaylist()
		end
	end

end

function Instance:Login()
	print(os.getenv('SPOTIFY_PORT'))
	self.webSocket:send('{"action": "login"}')
end

function Instance:Play(playlist_uri)
	local device_name = self.properties.Settings.Device:find("PlaybackDevice"):getValue()
	local playlist_arg = ""
	if playlist_uri then
		playlist_arg = '", "playlist_uri": "' .. playlist_uri
	end
	self:send('{"action": "play", "data": {"device_name": "' .. device_name .. playlist_arg .. '"}}')
end

function Instance:Pause()
	self:send('{"action": "pause"}')
end

function Instance:Next()
	self:send('{"action": "next"}')
end

function Instance:Previous()
	self:send('{"action": "previous"}')
end

function Instance:onShuffleUpdate()
	self:send('{"action": "update", "data": {"shuffle_state": ' .. tostring(self.properties.Controls.Modes:find("Shuffle"):getValue()) .. '}}')
end

function Instance:onRepeatUpdate()
	self:send('{"action": "update", "data": {"repeat_state": "' .. self.properties.Controls.Modes:find("Repeat"):getValue() .. '"}}')
end

function Instance:onVolumeUpdate()
	self:send('{"action": "update", "data": {"volume": ' .. self.properties.Controls:find("Volume"):getValue() .. '}}')
end

function Instance:onSongChanged(data)
	local tblImages = {}
	tblImages["Profile Image"] = data.item.album.images[2].url
	self.UserImageGroup:setObjects(tblImages)
	self.properties.Alerts.onSongChange:raise()
end

function Instance:RefreshDevices()
	self:send('{"action": "get_devices"}')
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

function Instance:PlayPlaylist()
	self:Play(self.playlists[self.properties.Controls:find("Playlist"):getValue()])
end

function Instance:disconnect()
	if (self.webSocket and self.webSocket:isConnected()) then
		self:send("disconnect", "unload")
		if (self.webSocket) then
			self.webSocket:disconnect()
		end
	end
end
