require "imagegroup"

Instance.devices = {}
local repeat_states = { track='Song', context='Enabled', off='Disabled' }
local url_regex = "/^[a-z](?:[-a-z0-9\\+\\.])*:(?:\\/\\/(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:])*@)?(?:\\[(?:(?:(?:[0-9a-f]{1,4}:){6}(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|::(?:[0-9a-f]{1,4}:){5}(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|(?:[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){4}(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|(?:(?:[0-9a-f]{1,4}:){0,1}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){3}(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|(?:(?:[0-9a-f]{1,4}:){0,2}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:){2}(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|(?:(?:[0-9a-f]{1,4}:){0,3}[0-9a-f]{1,4})?::[0-9a-f]{1,4}:(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|(?:(?:[0-9a-f]{1,4}:){0,4}[0-9a-f]{1,4})?::(?:[0-9a-f]{1,4}:[0-9a-f]{1,4}|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3})|(?:(?:[0-9a-f]{1,4}:){0,5}[0-9a-f]{1,4})?::[0-9a-f]{1,4}|(?:(?:[0-9a-f]{1,4}:){0,6}[0-9a-f]{1,4})?::)|v[0-9a-f]+\\.[-a-z0-9\\._~!\\$&'\\(\\)\\*\\+,;=:]+)\\]|(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\\.(?:[0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])){3}|(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=])*)(?::[0-9]*)?(?:\\/(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@]))*)*|\\/(?:(?:(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@]))+)(?:\\/(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@]))*)*)?|(?:(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@]))+)(?:\\/(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@]))*)*|(?!(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@])))(?:\\?(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@])|[\\x{E000}-\\x{F8FF}\\x{F0000}-\\x{FFFFD}\\x{100000}-\\x{10FFFD}\\/\\?])*)?(?:\\#(?:(?:%[0-9a-f][0-9a-f]|[-a-z0-9\\._~\\x{A0}-\\x{D7FF}\\x{F900}-\\x{FDCF}\\x{FDF0}-\\x{FFEF}\\x{10000}-\\x{1FFFD}\\x{20000}-\\x{2FFFD}\\x{30000}-\\x{3FFFD}\\x{40000}-\\x{4FFFD}\\x{50000}-\\x{5FFFD}\\x{60000}-\\x{6FFFD}\\x{70000}-\\x{7FFFD}\\x{80000}-\\x{8FFFD}\\x{90000}-\\x{9FFFD}\\x{A0000}-\\x{AFFFD}\\x{B0000}-\\x{BFFFD}\\x{C0000}-\\x{CFFFD}\\x{D0000}-\\x{DFFFD}\\x{E1000}-\\x{EFFFD}!\\$&'\\(\\)\\*\\+,;=:@])|[\\/\\?])*)?$/i"
local current_song_time = nil
local current_song_duration = nil
local current_vol = nil


Instance.properties = properties({
	{ name="Login", type="Action" },
	{ name="Logout", type="Action" },
	{ name="ConnectedAs", type="Text", value="Disconnected", ui={readonly=true} },
	{ name="Settings", type="PropertyGroup", ui = { expand = false }, items={
		{ name="Device", type="PropertyGroup", ui = { expand = true }, items={
			{ name="PlaybackDevice", type="Enum", items=Instance.devices, onUpdate="onDeviceUpdate" },
			{ name="RefreshDevices", type="Action" }
		}},
		{ name = "Modes", type = "PropertyGroup", items = {
			{ name = "Shuffle", type = "Bool", value = false, onUpdate = "onShuffleUpdate" },
			{ name = "Repeat", type = "Enum", items = { "Disabled", "Enabled", "Song" }, value = 'Disabled', onUpdate = "onRepeatUpdate" }
		}},
		{ name = "Volume", type = "Real", units = "NormalPercent", range = { min = 0.0, max = 1.0 },
		  	value = 1.0, onUpdate = "onVolumeUpdate" }
	}},
	{ name="Controls", type="PropertyGroup", ui={expand=false}, items= {
		{ name = "Play", type = "Action" },
		{ name = "Pause", type = "Action" },
		{ name = "Next", type = "Action" },
		{ name = "Previous", type = "Action" },
	}},
	{ name="DefaultPlaylist", type="PropertyGroup", ui={expand=false}, items= {
		{ name = "Playlist", type = "Enum", items = { "No Playlists" } },
		{ name = "RefreshPlaylists", type = "Action" },
		{ name = "PlayPlaylist", type = "Action" }
	}},
	{ name="Events", type="PropertyGroup", ui={expand=false}, items={
		{ name="onPlayingStarted", type="Alert", args={
			song_name="[Song]",
			artist="[Artist]",
			album_image_url="[URL]",
			album_name="[Album]"} },
		{ name="onPlayingStopped", type="Alert" },
		{ name="onSongChange", type="Alert", args={
			song_name="[Song]",
			artist="[Artist]",
			album_image_url="[URL]",
			album_name="[Album]"} },
		{ name="onSongTimeUpdate", type="Alert", args={
			current_time="[00:00]",
			duration="[00:00]",
			time_remaining="[00:00]"
		}}
	}}
})

function pad(time, units)
	if (not units) then
		units = "00"
	end

	local str = tostring(time)
	if (time<10 and #units>1) then
		str = "0" .. str
	end
	return str
end

function getMinsAndSecs(total_secs)
	return math.floor(total_secs / 60), math.floor(total_secs % 60)
end

function Instance:onInit()
	self.UserImageGroup = createImageGroup(self:getObjectKit(), "UserImageGroup")
	print(getLocalFolder() .. "ppspotify .exe")
	getOS():run("Spotify Service", getLocalFolder() .. "ppspotify .exe")

	getUI():setUIProperty({
		{ obj=self.properties:find("Logout"), visible=false },
		{ obj=self.properties:find("ConnectedAs"), visible=false }
	})
	self.properties.ConnectedAs = ""
	self:connect()

	local tblImages = {}
	tblImages["Profile Image"] = getLocalFolder() .. "blank.png"
	self.UserImageGroup:setObjects(tblImages)

end

function Instance:send(cmd)
	for retries=1, 5 do
		if self.webSocket and self.webSocket:isConnected() then
			self.webSocket:send(cmd)
			break
		end
	end
end

function Instance:send_action(action, data)
	if data then
		return self:send(json.encode({ action, data }))
	end

	self:send(json.encode({ action }))
end

function Instance:connect()
	self:attemptConnection()
end

function Instance:attemptConnection()
	local host = getNetwork():getHost("localhost")
	self.webSocket = host:openWebSocket("ws://localhost:38045/ws")
	self.webSocket:setAutoReconnect(true)

	self.webSocket:addEventListener("onMessage", self, self.onMessage)
	self.webSocket:addEventListener("onConnected", self, self._onWsConnected)
	self.webSocket:addEventListener("onDisconnected", self, self._onWsDisconnected)

end

function Instance:_onWsConnected()
	local config = self:getConfig()
	if config then
		local client_id, client_secret = config.client_id, config.client_secret
		if client_id and client_secret then
			self:send('{"action": "login", "data": {"client_id": "' ..
				client_id .. '", "client_secret": "' ..
				client_secret .. '"}}')
		end
	end
end

function Instance:_onWsDisconnected()

end

function Instance:onSpotifyConnect(data)
	getUI():setUIProperty({
		{ obj=self.properties:find("Controls"), expand=true },
		{ obj=self.properties:find("Events"), expand=true },
		{ obj=self.properties:find("Logout"), visible=true },
		{ obj=self.properties:find("Login"), visible=false },
		{ obj=self.properties:find("ConnectedAs"), visible=true }
	})

	self.properties.ConnectedAs = tostring(data.name)
	self:setConfig({ client_id=data.client_id, client_secret=data.client_secret })
	self.devices.all_devices =data.devices
	self.properties.Settings.Device:find("PlaybackDevice"):setElements(self.devices.all_devices)

	--[[
	local tblImages = {}
	tblImages["Album Image"] =data.user_image_url
	self.UserImageGroup:setObjects(tblImages)
	--]]
	self:onRefreshPlaylists(data)

	if not self.devices.current_device then
		self.devices.current_device =data.current_device
	end

	self.properties.Settings.Modes.Shuffle = data.shuffle_state
	self.properties.Settings.Modes:find("Repeat").value = repeat_states[data.repeat_state]

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

	if action == 'spotify_connect' then
		self:onSpotifyConnect(data)
	elseif action == 'song_changed' then
		self:onSongChanged(data)
	elseif action == 'update' then
		self:onUpdateSettings(data)
	elseif action == 'started_playing' then
		self:onPlay(data)
	elseif action == 'playing_stopped' then
		self:onPause()
	elseif action == 'devices' then
		self.devices.all_devices = data.devices
		self.properties.Settings.Device:find("PlaybackDevice"):setElements(self.devices.all_devices)
	elseif action == 'playlists' then
		self:onRefreshPlaylists(data)
	elseif action == 'error' then
		local command = data.command
		if command == 'play' then
			self.devices.current_device = nil
			self:PlayPlaylist()
		end
	elseif action == 'restart_me' then
		getOS():run("Spotify Service", getLocalFolder() .. "ppspotify.exe")
	end
end

function Instance:Login()
	self:send_action("login")
end

function Instance:Play(playlist_uri)
	local device_name = self.properties.Settings.Device:find("PlaybackDevice"):getValue()

	if playlist_uri then
		self:send_action("play", { device_name=device_name, playlist_uri=playlist_uri })
	end

	self:send_action("play", { device_name=device_name })
end

function Instance:RefreshPlaylists()
	self:send_action("refresh_playlists")
end

function Instance:Pause()
	self:send_action("pause")
end

function Instance:Next()
	self:send_action("next")
end

function Instance:Previous()
	self:send_action("previous")
end

function Instance:onShuffleUpdate()
	self:send_action("update", {
		shuffle_state=self.properties.Settings.Modes:find("Shuffle"):getValue( )
	} )
end

function Instance:onRepeatUpdate()
	self:send_action("update", {
		shuffle_state=self.properties.Settings.Modes:find("Shuffle"):getValue( )
	} )
end

function Instance:onVolumeUpdate()
	local new_volume = math.floor(
		self.properties.Settings:find("Volume"):getValue( ) * 100 / 20
	) * 20

	if current_vol ~= new_volume then
		self:send_action("update", {volume=new_volume})
		current_vol = new_volume
	end
end

function Instance:onRefreshPlaylists(data)
	self.playlists = data.playlists
	local playlists = {}

	for name, _ in pairs(data.playlists) do
		table.insert(playlists, name)
	end

	self.properties.DefaultPlaylist:find("Playlist"):setElements(playlists)
end

function Instance:onSongChanged(data)
	local tblImages = {}
	tblImages["Album Image"] = data.item.album.images[2].url
	self.UserImageGroup:setObjects(tblImages)

	self.properties.Events.onSongChange:raise({
		song_name = data.item.name,
		artist = data.item.artists[1].name,
		album_image_url = data.item.album.images[2].url,
		album_name = data.item.artists[1].name
	})
	current_song_duration = math.floor(data.item.duration_ms / 1000)
	current_song_time = math.floor(data.progress_ms / 1000)
	getAnimator():stopTimer(self, self.updateDuration)
	getAnimator():createTimer(self, self.updateDuration, seconds(1), true)
end

function Instance:updateDuration()
	if not current_song_time or current_song_duration - current_song_time == 0 then
		getAnimator():stopTimer(self, self.updateDuration)
		return
	end
	local current_mins, current_secs = getMinsAndSecs(current_song_time)
	local remaining_mins, remaining_secs = getMinsAndSecs(current_song_duration - current_song_time)
	local duration_mins, duration_secs = getMinsAndSecs(current_song_duration)
	self.properties.Events.onSongTimeUpdate:raise({
		current_time = pad(current_mins) .. ":" .. pad(current_secs),
		duration = pad(duration_mins) .. ":" .. pad(duration_secs),
		time_remaining = pad(remaining_mins) .. ":" .. pad(remaining_secs),
	})
	current_song_time = current_song_time + 1
end

function Instance:RefreshDevices()
	self:send_action("refresh_devices")
end

function Instance:onPlay(data)
	local tblImages = {}
	tblImages["Album Image"] = data.item.album.images[2].url
	self.UserImageGroup:setObjects(tblImages)

	self.properties.Events.onPlayingStarted:raise({
	song_name = data.item.name,
	artist = data.item.artists[1].name,
	album_image_url = data.item.album.images[2].url,
	album_name = data.item.artists[1].name
	})
	current_song_duration = math.floor(data.item.duration_ms / 1000)
	current_song_time = math.floor(data.progress_ms / 1000)
	getAnimator():stopTimer(self, self.updateDuration)
	getAnimator():createTimer(self, self.updateDuration, seconds(1), true)
end

function Instance:onPause()
	getAnimator():stopTimer(self, self.updateDuration)
	self.properties.Events.onPlayingStopped:raise()
	local tblImages = {}
	tblImages["Profile Image"] = getLocalFolder() .. "blank.png"
	self.UserImageGroup:setObjects(tblImages)
end

function Instance:onUpdateSettings(data)
	if data.shuffle_state ~= nil then
		self.properties.Settings.Modes.Shuffle = data.shuffle_state
	end
	if data.repeat_state then
		self.properties.Settings.Modes:find("Repeat"):setValue(repeat_states[data.repeat_state])
	end
	if data.volume then
		self.properties.Settings.Volume = data.volume
	end
end

function Instance:PlayPlaylist()
	if self.playlists then
		self:Play(self.playlists[self.properties.DefaultPlaylist:find("Playlist"):getValue()])
	end
end

function Instance:disconnect()
	if (self.webSocket and self.webSocket:isConnected( )) then
		self:send_action("disconnect")
		if (self.webSocket) then
			self.webSocket:disconnect( )
		end
	end
end